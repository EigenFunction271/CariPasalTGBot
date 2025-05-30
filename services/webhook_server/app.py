import os
import logging
import sys
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import httpx
import asyncio
from concurrent.futures import ThreadPoolExecutor

# --- Logging Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('webhook_server.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# --- Environment Setup ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BOT_SERVICE_URL = os.getenv('BOT_SERVICE_URL')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
if not BOT_SERVICE_URL:
    raise ValueError("BOT_SERVICE_URL environment variable is not set")

# --- Flask App ---
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=4)

async def forward_to_bot_service(update):
    """Forward update to bot service asynchronously."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BOT_SERVICE_URL}/webhook",
            json=update,
            headers={"X-Telegram-Bot-Token": TELEGRAM_BOT_TOKEN}
        )
        response.raise_for_status()
        return response

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring."""
    return jsonify({"status": "healthy"}), 200

@app.route('/', methods=['POST'])
def telegram_webhook():
    """Forward Telegram webhook updates to the bot service."""
    try:
        # Get the update from Telegram
        update = request.get_json(force=True)
        
        # Log the update (excluding sensitive data)
        chat_id = update.get('message', {}).get('chat', {}).get('id') or \
                 update.get('callback_query', {}).get('message', {}).get('chat', {}).get('id')
        logger.info(f"Received update for chat_id: {chat_id if chat_id else 'Unknown'}")
        
        # Run async operation in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response = loop.run_until_complete(forward_to_bot_service(update))
            return jsonify({"status": "ok"}), 200
        finally:
            loop.close()
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error forwarding to bot service: {e.response.status_code} - {e.response.text}")
        return jsonify({"status": "error", "message": "Error forwarding to bot service"}), 500
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 