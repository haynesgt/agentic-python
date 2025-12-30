import asyncio
import enum
import logging
import os
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, TypedDict, TypeVar

import logfire
from pydantic import BaseModel
from pydantic_ai import Agent, WebFetchTool, WebSearchTool
from pydantic_ai.models.openai import OpenAIResponsesModel
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

T = TypeVar("T")
U = TypeVar("U")

type EventBusHandler = Callable[[U], Awaitable[None]]


class AsyncEventBus(Generic[T, U]):
    _handlers: defaultdict[T, set[EventBusHandler[U]]]

    def __init__(self):
        self._handlers = defaultdict(set[EventBusHandler[U]])

    def on(self, event_type: T, fn: EventBusHandler[U]) -> None:
        self._handlers[event_type].add(fn)

    def off(self, event_type: T, fn: EventBusHandler[U]) -> None:
        self._handlers[event_type].discard(fn)

    @contextmanager
    def onoff(self, event_type: T, fn: EventBusHandler[U]) -> Iterator[None]:
        self.on(event_type, fn)
        yield
        self.off(event_type, fn)

    def emit(self, event_type: T, payload: U) -> asyncio.Future[Any]:
        return asyncio.gather(
            *(fn(payload) for fn in self._handlers[event_type]),
            return_exceptions=True,
        )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


logfire.configure()
logfire.instrument_pydantic_ai()

"""
Thinking in terms of global state and events, we have:
on_event: global_state, event -> new_global_state

the global state consists of:
- all past events
- all past external actions
- current actions
- all scheduled future actions

An action may be:
- send message
- ask ai for next action

Since the function happens at a particular time, we need to translate state changes into what to do now:
- future task execution:
    1. a worker can look at the next future action, then sleep until that time, and execute it
    2. or we can use async functions to wait-and-act, but with cancellation support
As well, function execution is not instantaneous:
1. we can simplify by locking certain tasks within a context
"""

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.2")

events: dict[int, asyncio.Event] = {}


def add_event(event: asyncio.Event) -> int:
    new_id = id(event)
    events[new_id] = event
    return new_id


def remove_event(event: asyncio.Event):
    event_id = id(event)
    if event_id in events:
        del events[event_id]


class Conversation(BaseModel):
    class EventType(enum.Enum):
        USER_MESSAGE = "user_message"
        BOT_MESSAGE = "bot_message"
        AGENT_START = "agent_start"

    class Event(TypedDict, total=False):
        type: str
        text: str | None
        timestamp: str

    events: list[Event] = []
    cancel_events: list[int] = []
    event_bus: AsyncEventBus[EventType, Event] = AsyncEventBus()

    def cancel_all(self, except_event: asyncio.Event | None = None):
        for event_id in self.cancel_events:
            event = events.get(event_id)
            if event is not None and event is not except_event:
                event.set()
                remove_event(event)
        self.cancel_events = []


conversations: defaultdict[int, Conversation] = defaultdict(lambda: Conversation())


def escape_markdown_v2(text: str) -> str:
    escape_chars = r"\_[]()~>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(update)
    assert update.effective_chat is not None
    chat_id = update.effective_chat.id
    message = update.message
    assert message is not None
    user_text = (message.text or "").strip()
    cancel_event = asyncio.Event()

    conversation = conversations[chat_id]
    conversation.events.append(
        {
            "type": "user_message",
            "text": user_text,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    conversation.cancel_events.append(add_event(cancel_event))
    conversation.event_bus.emit(Conversation.EventType.USER_MESSAGE, {"text": user_text})
    asyncio.create_task(context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING))

    async def wait_seconds(seconds: float):
        await asyncio.sleep(seconds)

    async def wait_until_time(iso_time: str):
        target_time = datetime.fromisoformat(iso_time).astimezone(UTC)
        now = datetime.now(UTC)
        delay = (target_time - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    async def wait_until_seconds_after_time(iso_time: str, seconds: float):
        target_time = datetime.fromisoformat(iso_time).astimezone(UTC)
        target_time += timedelta(seconds=seconds)
        now = datetime.now(UTC)
        delay = (target_time - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    async def start_message() -> int:
        """
        Starts a message by sending "..." and returning the message ID to be edited later.
        """
        logger.info("Starting message...")
        asyncio.create_task(context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING))
        msg = await context.bot.send_message(chat_id=chat_id, text="...")
        return msg.id

    async def send_message(text: str, msg_id: int | None = None) -> str:
        """
        Sends or edits a message with the given text.
        """
        logger.info(f"Sending message: {text}")
        conversation.events.append(
            {
                "type": "bot_message",
                "text": text,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        if msg_id is not None:
            asyncio.create_task(
                context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=escape_markdown_v2(text),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            )
        else:
            asyncio.create_task(
                context.bot.send_message(
                    chat_id=chat_id, text=escape_markdown_v2(text), parse_mode=ParseMode.MARKDOWN_V2
                )
            )
        return "message sent"

    async def cancel_other_agents():
        conversation.cancel_all(except_event=cancel_event)

    agent = Agent(
        model=OpenAIResponsesModel(MODEL_NAME),
        system_prompt=(
            "You are a helpful assistant chatting on Telegram. "
            "Do not escape MarkdownV2 formatting (it will be handled automatically). Do not escape !?().-[] or anything else. "
            "Be concise, ask clarifying questions when needed. "
            "Send multiple extremely short messages using send_message rather than one long message. Use MarkdownV2 formatting. "
            "Split responses across multiple messages instead of using line breaks. "
            "The final output will be not sent as a message. Only use send_message to send messages. "
            "Do not send duplicate messages. You have a tendancy to repeat yourself, avoid this. "
            "For the final output, output one or two words as a status log. "
            "wait_ methods will block you until they complete, so you will usually want to send a message before waiting. "
            "If you will be sending multiple messages, for each message after the first, start with start_message to get a message ID,"
            " then use that ID in subsequent send_message calls. "
            "Do not include anything like citeturn0search8turn0search7 in your messages, which might come from search tool. "
        ),
        tools=[
            wait_seconds,
            wait_until_time,
            wait_until_seconds_after_time,
            start_message,
            send_message,
            cancel_other_agents,
        ],
        builtin_tools=[WebSearchTool(), WebFetchTool()],
    )

    async def run():
        conversation.events.append(
            {
                "type": "agent_start",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        result = await agent.run(
            user_prompt=conversation.model_dump_json(),
        )
        logger.info("Result: %s", result)
        cancel_event.set()
        remove_event(cancel_event)

    run_task = asyncio.create_task(run())

    async def handle_cancellation():
        await cancel_event.wait()
        if not run_task.done():
            run_task.cancel()

    asyncio.create_task(handle_cancellation())


def main() -> None:
    TELEGRAM_BOT_KEY = os.getenv("TELEGRAM_BOT_KEY")
    assert TELEGRAM_BOT_KEY, "Please set TELEGRAM_BOT_KEY."
    app = ApplicationBuilder().token(TELEGRAM_BOT_KEY).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
