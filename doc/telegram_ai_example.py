import asyncio
import logging
import os
from collections import defaultdict
from io import BytesIO

from openai import AsyncOpenAI
from pydantic_ai import Agent, AgentRunResult, WebSearchTool
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIResponsesModel
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise OSError(f"Please set the {var_name} environment variable.")
    return value


BOT_TOKEN = require_env("TELEGRAM_BOT_KEY")

# If you use OpenAI via pydantic-ai, you'll typically want OPENAI_API_KEY set too.
# Optional: OPENAI_MODEL env var (default below).
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# In-memory chat history per chat_id
histories: defaultdict[int, list[ModelMessage]] = defaultdict(list)
stop_events: defaultdict[int, asyncio.Event] = defaultdict(asyncio.Event)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_queue_awaitable = asyncio.locks.Event()
    assert update.effective_chat is not None
    assert update.message is not None

    chat_id = update.effective_chat.id
    message = update.message
    assert message.text is not None
    user_text = message.text.strip()

    async def respond():
        if not user_text:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        def ring_bell():
            print("Ding ding ding!")

        def release_message_lock():
            message_queue_awaitable.set()

        async def wait_a_bit(seconds: float):
            message_queue_awaitable.set()
            await asyncio.sleep(seconds)

        async def send_message(text: str):
            await message.reply_text(
                text,
            )

        agent = Agent(
            model=OpenAIResponsesModel(MODEL_NAME),
            system_prompt=(
                "You are a helpful assistant chatting on Telegram. "
                "Be concise, ask clarifying questions when needed."
            ),
            tools=[ring_bell, release_message_lock, wait_a_bit, send_message],
            builtin_tools=[WebSearchTool()],
        )
        result: AgentRunResult = await agent.run(
            user_prompt=user_text,
            message_history=histories[chat_id],
        )
        if result.output:
            await message.reply_text(
                result.output,
            )
        histories[chat_id].extend(result.new_messages())
        message_queue_awaitable.set()

    asyncio.create_task(respond())
    await message_queue_awaitable.wait()


oai = AsyncOpenAI()


async def on_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.message.text:
        return

    prompt = update.message.text.removeprefix("/image").strip()
    if not prompt:
        await update.message.reply_text("Usage: /image a cozy cabin in the snow")
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        # Example: generate image, get base64, send as photo
        resp = await oai.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
            prompt=prompt,
            size="1024x1024",
            quality="low",
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

        await update.message.reply_photo(photo=bio, caption=prompt)
    except Exception as e:
        await update.message.reply_text(f"Image failed: {type(e).__name__}: {e}")


def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CommandHandler("image", on_image))
    app.run_polling()


if __name__ == "__main__":
    main()
