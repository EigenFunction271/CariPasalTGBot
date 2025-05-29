import requests
import time
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ping_service.log')
    ]
)
logger = logging.getLogger(__name__)

def ping_service():
    """Ping the service to keep it alive."""
    url = os.getenv('WEBHOOK_URL', '').rstrip('/') + '/ping'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            logger.info(f"Ping successful at {datetime.now()}")
        else:
            logger.error(f"Ping failed with status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error pinging service: {e}")

def main():
    """Main function to run the ping service."""
    logger.info("Starting ping service...")
    while True:
        ping_service()
        # Sleep for 14 minutes (840 seconds) to ensure we ping before the 15-minute timeout
        time.sleep(840)

if __name__ == '__main__':
    main() 