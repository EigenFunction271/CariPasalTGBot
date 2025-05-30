import os
import logging
import sys
from typing import Dict, Any

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

# --- Environment Variables ---
REQUIRED_ENV_VARS = [
    'TELEGRAM_BOT_TOKEN',
    'BOT_SERVICE_URL',
]

# --- Constants ---
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
REQUEST_TIMEOUT = 30  # seconds 