import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from pathlib import Path
import threading
import asyncio

# Always load .env from the project root, regardless of current working directory
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logging.getLogger("telegram").setLevel(logging.DEBUG)
logging.getLogger("telegram.ext").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

app = Flask(__name__)
ptb_app = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Start handler triggered")
    await update.message.reply_text("Hello from webhook!")

ptb_app.add_handler(CommandHandler("start", start))

def run_ptb_app():
    """Run the PTB application in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Initialize the application
        loop.run_until_complete(ptb_app.initialize())
        logger.info("PTB application initialized")
        
        # Start the application
        loop.create_task(ptb_app.start())
        logger.info("PTB application started")
        
        # Keep the event loop running
        loop.run_forever()
    except Exception as e:
        logger.error(f"Error in PTB thread: {e}", exc_info=True)
    finally:
        loop.close()

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        logger.info("Webhook called")
        data = request.get_json(force=True)
        logger.info(f"Webhook received data: {data}")
        update = Update.de_json(data, ptb_app.bot)
        ptb_app.update_queue.put_nowait(update)
        return "ok", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return f"Webhook error: {e}", 500

@app.route("/", methods=["GET"])
def root():
    return "Bot is running!", 200

def main():
    # Start PTB app in background thread (only once)
    ptb_thread = threading.Thread(target=run_ptb_app, daemon=True)
    ptb_thread.start()
    logger.info("PTB thread started")
    
    # Set webhook before starting Flask
    import asyncio
    asyncio.run(ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook"))
    logger.info("Webhook set. Starting Flask app.")
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
