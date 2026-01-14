import asyncio
import enum
import logging
import os
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any, Generic, Literal, TypedDict, TypeVar

import logfire
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, WebSearchTool
from pydantic_ai.models.openai import OpenAIResponsesModel
from telegram import InputMediaPhoto, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

T = TypeVar("T")
U = TypeVar("U")

type EventBusHandler[U] = Callable[[U], Awaitable[None]]


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


class EventType(enum.Enum):
    USER_MESSAGE = "user_message"
    BOT_MESSAGE = "bot_message"
    AGENT_START = "agent_start"
    STARTED_GENERATING_IMAGE = "started_generating_image"
    FINISHED_GENERATING_IMAGE = "finished_generating_image"


class EventRecord(TypedDict, total=False):
    type: str
    from_user: str | None
    text: str | None
    timestamp: str
    data: dict[str, Any] | None


class NoteRecord(BaseModel):
    value: str
    date: datetime
    priority: float


class ConversationHistory(BaseModel):
    chat_id: int
    events: list[EventRecord] = []
    notes: dict[str, str] = {}
    note_records: dict[str, NoteRecord] = {}

    @staticmethod
    def load_history(chat_id: int) -> "ConversationHistory":
        conversation_file = f"./conversations/{chat_id}.json"
        if os.path.exists(conversation_file):
            with open(conversation_file) as f:
                return ConversationHistory.model_validate_json(f.read())
        return ConversationHistory(chat_id=chat_id)

    def save_history(self) -> None:
        conversation_file = f"./conversations/{self.chat_id}.json"
        os.makedirs(os.path.dirname(conversation_file), exist_ok=True)
        with open(conversation_file, "w") as f:
            f.write(self.model_dump_json(indent=2))

    def add_event(self, event: EventRecord) -> None:
        self.events.append(event)
        self.save_history()

    def save_note(self, key: str, value: str | None, priority: float = 0.0) -> None:
        if value is None or value == "":
            if key in self.notes:
                del self.notes[key]
            if key in self.note_records:
                del self.note_records[key]
        else:
            self.note_records[key] = NoteRecord(
                value=value, date=datetime.now(UTC), priority=priority
            )
        self.save_history()


class Conversation:
    history: "ConversationHistory"
    cancel_events: list[int] = []
    event_bus: AsyncEventBus[EventType, EventRecord] = AsyncEventBus()

    def __init__(self, chat_id: int):
        self.history = ConversationHistory.load_history(chat_id)

    def cancel_all(self, except_event: asyncio.Event | None = None):
        for event_id in self.cancel_events:
            event = events.get(event_id)
            if event is not None and event is not except_event:
                event.set()
                remove_event(event)
        self.cancel_events = []


conversations: dict[int, Conversation] = {}

oai = AsyncOpenAI()


def escape_markdown_v2(text: str) -> str:
    escape_chars = r"\_[]()~>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


type ImageQuality = Literal["low", "medium", "high"]


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def indicate_typing():
        asyncio.create_task(context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING))

    logger.info(update)
    assert update.effective_chat is not None
    chat_id = update.effective_chat.id
    message = update.message
    assert message is not None
    user_text = (message.text or "").strip()
    cancel_event = asyncio.Event()

    if chat_id not in conversations:
        conversations[chat_id] = Conversation(chat_id=chat_id)

    conversation = conversations[chat_id]
    conversation.history.add_event(
        {
            "type": EventType.USER_MESSAGE.value,
            "from_user": f"{message.from_user.full_name} ({message.from_user.id})"
            if message.from_user
            else "unknown",
            "text": user_text,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    conversation.cancel_events.append(add_event(cancel_event))
    conversation.event_bus.emit(EventType.USER_MESSAGE, {"text": user_text})
    indicate_typing()

    async def wait_seconds(seconds: float) -> str:
        # await context.bot.send_message(chat_id=chat_id, text=f"waiting for {seconds} seconds")
        await asyncio.sleep(seconds)
        return "wait completed. say something interesting, and then wait even longer!"

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

    async def send_message(text: str, msg_id: int | None = None) -> str:
        """
        Sends or edits a message with the given text.
        """
        logger.info(f"Sending message: {text}")
        conversation.history.add_event(
            {
                "type": EventType.BOT_MESSAGE.value,
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

    async def generate_and_send_image(
        prompt: str, quality: ImageQuality = "low", caption: str = ""
    ) -> None:
        """
        Generates an image based on the prompt and sends it to the chat.

        The caption is sent along with the image.
        """
        logger.info(f"Generating image: {prompt=} {quality=} {caption=}")

        conversation.history.add_event(
            {
                "type": EventType.STARTED_GENERATING_IMAGE.value,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"prompt": prompt, "quality": quality, "caption": caption},
            }
        )

        indicate_typing()
        new_message = await message.reply_text(
            f"Generating image: {caption}. This may take a minute."
        )

        try:
            # Example: generate image, get base64, send as photo
            indicate_typing()
            resp = await oai.images.generate(
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
                prompt=prompt,
                size="1024x1024",
                quality=quality,
                background="transparent",
                moderation="low",
            )
            if not resp.data or len(resp.data) == 0:
                raise ValueError("No image data received")

            b64 = resp.data[0].b64_json
            if not b64:
                raise ValueError("No image data received")

            import base64

            img_bytes = base64.b64decode(b64)
            bio = BytesIO(img_bytes)
            bio.name = "image.png"
            await new_message.edit_media(media=InputMediaPhoto(media=bio, caption=caption))

            # await message.reply_photo(photo=bio, caption=caption)
        except Exception as e:
            await new_message.edit_text(f"Image failed: {type(e).__name__}: {e}")
            # await message.reply_text(f"Image failed: {type(e).__name__}: {e}")

    def save_note(key: str, value: str | None, priority: float = 0.0) -> None:
        """
        Saves a note. Set value to empty string or None to delete the note. (literal null not string 'None')

        :param key: note id
        :type key: str
        :param value: Description
        :type value: str | None
        :param priority: priority from 0 to 1
        :type priority: float
        """
        conversation.history.save_note(key, value, priority)
        logger.info(f"Saved note: {key}={value} with priority={priority}")

    def debug_warning_for_developer(msg: str) -> None:
        """
        Warns the developer with a debug message. Use this if something unexpected happens.
        """
        logger.warning(f"DEBUG WARNING FOR DEVELOPER: {msg}")
        asyncio.create_task(context.bot.send_message(chat_id=chat_id, text=f"WARNING: {msg}"))
        conversation.history.add_event(
            {
                "type": "debug_warning",
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"message": msg},
            }
        )

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
            " then use that ID in subsequent send_message calls. "
            "Do not include anything like citeturn0search8turn0search7 in your messages, which might come from search tool. "
            "After sending a message, wait for a while and send a follow up. If the user sends a message it will cancel your wait. "
            "After responding, wait 15 seconds and send a follow up. Then, repeatedly roughly twice as long and send another follow up. Do this indefinitely. ALWAYS wait and then respond with a follow up. e.g. respond, wait 60, follow up, wait 120, follow up, wait 240, follow up, etc. to no limit. Make the follow ups more and more creative and off topic as the user doesn't respond. "
            "Don't worry if the wait function doesn't seem to be working. It is probably in test mode. "
            "If the user asks for an image, send a short message before generating images since it takes a few seconds to generate the image. "
            "Avoid starting multiple messages in parallel as this can lead them to arrive out of order. "
            "After responding be eager to take new notes from the user and save them using save_note. Save many notes about the user's preferences and interests. You don't need to note things you don't need to remember. "
            "Never forget to wait and then follow up after each response as well as after each follow up you send! "
            "Try not to save more than 30 notes in total to reduce costs. Prioritize high priority notes and recent notes. "
        ),
        tools=[
            wait_seconds,
            wait_until_time,
            wait_until_seconds_after_time,
            send_message,
            cancel_other_agents,
            generate_and_send_image,
            save_note,
            debug_warning_for_developer,
        ],
        builtin_tools=[WebSearchTool()],  # , WebFetchTool()],
    )

    run_task: asyncio.Task[None]

    async def cancel_on_update(_: Any) -> None:
        run_task.cancel()

    async def run():
        with conversation.event_bus.onoff(EventType.USER_MESSAGE, cancel_on_update):
            conversation.history.add_event(
                {
                    "type": EventType.AGENT_START.value,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            result = await agent.run(
                user_prompt=conversation.history.model_dump_json()[-10000:],
            )
            logger.info("Result: %s", result)
            cancel_event.set()
            remove_event(cancel_event)

    run_task = asyncio.create_task(run())

    async def handle_cancellation():
        await asyncio.wait(
            [asyncio.create_task(cancel_event.wait()), run_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
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
