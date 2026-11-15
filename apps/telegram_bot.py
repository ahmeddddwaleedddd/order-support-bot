"""Telegram front-end. Talks only to the deployed API, never to the DB or LLM directly.
Install: pip install -e ".[telegram]"   Run: python apps/telegram_bot.py"""

import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
API_URL = os.environ.get("SUPPORT_API_URL", "http://localhost:8000").rstrip("/")
HEADERS = {"X-API-Key": os.environ["API_KEY"]}
# A local model can take minutes per reply (eval: p95 turn latency 326 s), so wait far
# longer than a normal API would.
HTTP_TIMEOUT = 600
sessions: dict[int, str] = {}  # chat_id -> session_id (in memory; lost on restart)

logging.basicConfig(level=logging.INFO)
# httpx logs every request URL at INFO, and Telegram's URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def keep_typing(bot, chat_id):
    """Telegram's 'typing...' lasts about 5 seconds, so refresh it until cancelled."""
    while True:
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            logging.warning("Typing indicator failed")
        await asyncio.sleep(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I can help with order status, cancellations and refunds.\n"
        "Try: \"I want a refund for order A1002, my email is jordan@example.com\".\n"
        "This is a demo with fake data. Replies can take a minute or two. "
        "Send /done when finished."
    )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session_id = sessions.pop(chat_id, None)
    if session_id is None:
        await update.message.reply_text(
            "There is no open conversation. Send a message to start one."
        )
        return
    typing = asyncio.create_task(keep_typing(context.bot, chat_id))
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            r = await http.post(f"{API_URL}/sessions/{session_id}/close", headers=HEADERS)
            r.raise_for_status()
        await update.message.reply_text(
            "Thanks! Your case has been saved. Send a message to start again."
        )
    except httpx.HTTPError:
        logging.exception("Closing the session failed")
        sessions[chat_id] = session_id  # keep it so /done can be retried
        await update.message.reply_text("Sorry, I couldn't save the case. Try /done again.")
    finally:
        typing.cancel()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    typing = asyncio.create_task(keep_typing(context.bot, chat_id))
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            r = await http.post(
                f"{API_URL}/chat", headers=HEADERS,
                json={"message": update.message.text[:2000],
                      "session_id": sessions.get(chat_id)},
            )
            r.raise_for_status()
        data = r.json()
        sessions[chat_id] = data["session_id"]
        await update.message.reply_text((data["reply"] or "…")[:4000])
    except httpx.HTTPError:
        logging.exception("API call failed")
        await update.message.reply_text("Sorry, I'm having trouble right now. Please try again.")
    finally:
        typing.cancel()


def main():
    app = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE, on_text)
    )
    app.run_polling()


if __name__ == "__main__":
    main()