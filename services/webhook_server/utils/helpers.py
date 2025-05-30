import os
import asyncio
import httpx
from typing import Dict, Any, Optional
from .constants import logger, MAX_RETRIES, RETRY_DELAY, REQUEST_TIMEOUT, REQUIRED_ENV_VARS

async def forward_to_bot_service(update: Dict[str, Any], bot_token: str, bot_service_url: str) -> Optional[httpx.Response]:
    """
    Forward a Telegram update to the bot service with retries.
    
    Args:
        update: The Telegram update to forward
        bot_token: The Telegram bot token
        bot_service_url: The URL of the bot service
        
    Returns:
        The response from the bot service if successful, None otherwise
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{bot_service_url}/webhook",
                    json=update,
                    headers={"X-Telegram-Bot-Token": bot_token}
                )
                response.raise_for_status()
                return response
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error forwarding to bot service (attempt {attempt + 1}/{MAX_RETRIES}): {e.response.status_code} - {e.response.text}")
            if attempt == MAX_RETRIES - 1:
                raise
                
        except Exception as e:
            logger.error(f"Error forwarding to bot service (attempt {attempt + 1}/{MAX_RETRIES}): {e}", exc_info=True)
            if attempt == MAX_RETRIES - 1:
                raise
                
        await asyncio.sleep(RETRY_DELAY)
    
    return None

def validate_env_vars() -> None:
    """Validate that all required environment variables are set."""
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        critical_message = f"CRITICAL STARTUP FAILURE: Missing required environment variables: {', '.join(missing_vars)}"
        logger.critical(critical_message)
        raise ValueError(critical_message) 