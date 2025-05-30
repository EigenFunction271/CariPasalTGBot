import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .utils.constants import logger, REQUIRED_ENV_VARS
from .utils.helpers import forward_to_bot_service, validate_env_vars

# --- Environment Setup ---
load_dotenv()
validate_env_vars()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BOT_SERVICE_URL = os.getenv('BOT_SERVICE_URL')

# --- Flask App ---
app = Flask(__name__)

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
        
        # Forward to bot service
        response = forward_to_bot_service(update, TELEGRAM_BOT_TOKEN, BOT_SERVICE_URL)
        if response:
            return jsonify({"status": "ok"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to forward update"}), 500
            
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10001))  # Default to 10001 if PORT not set
    app.run(host='0.0.0.0', port=port) 