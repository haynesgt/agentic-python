import asyncio
import os

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_KEY")
assert BOT_TOKEN, "Please set the TELEGRAM_BOT_KEY environment variable."


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        print(update)
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )
        await asyncio.sleep(1)
        await update.message.reply_text(update.message.text)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.run_polling()


if __name__ == "__main__":
    main()
