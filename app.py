# app.py
import os
import logging
import sys
from typing import Dict, Any, List, Optional # Removed Tuple for now, can be added if specific functions return tuples

from dotenv import load_dotenv
from flask import Flask, request, jsonify # Standard Flask imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand # Telegram imports
from telegram.error import TelegramError # Specific error for handling
from telegram.ext import (
    Application,
    CommandHandler, # For /command
    MessageHandler, # For text, media etc.
    CallbackQueryHandler, # For inline button presses
    ContextTypes, # For type hinting context
    ConversationHandler, # For multi-step interactions
    filters, # For filtering message types
)
from pyairtable import Api, Table # For Airtable integration
import httpx # Modern HTTP client, used by PTB and for direct calls
from datetime import datetime, timezone # For timestamps
import asyncio # For async operations and Lock

from constants import (
    logger, PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, 
    GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED, SELECT_PROJECT, UPDATE_PROGRESS, 
    UPDATE_BLOCKERS, STATUS_OPTIONS, UPDATE_PROJECT_PREFIX, VIEW_PROJECT_PREFIX, 
    SELECT_PROJECT_PREFIX
)
from database import (
    projects_table, updates_table, get_user_projects_from_airtable,
    get_project_updates_from_airtable, format_project_summary_text
)
from handlers.new_project import (
    newproject_entry_point, project_name_state, project_tagline_state,
    problem_statement_state, tech_stack_state, github_link_state,
    project_status_state_callback, help_needed_state, cancel_conversation
)
from handlers.update_project import (
    handle_project_action_callback, update_progress_state, update_blockers_state, select_project_for_update
)
from handlers.myprojects import my_projects_command
from handlers.view_project import handle_project_action_callback as view_project_callback

# --- Logging Configuration ---
# Configure logging as early as possible
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s', # Added funcName and lineno
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to stdout for Render/Docker
        logging.FileHandler('bot.log', mode='a') # Append to a local log file
    ]
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
load_dotenv() # Load .env file if present (good for local dev)
logger.info("Attempted to load environment variables from .env file (if present).")

# --- Global Variables ---
# Telegram Application object - will be initialized lazily once per worker
application: Optional[Application] = None
application_lock = asyncio.Lock() # Lock to ensure thread-safe/greenlet-safe lazy initialization

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Airtable Configuration & Validation ---
# Validate required environment variables first
REQUIRED_ENV_VARS = [
    'TELEGRAM_BOT_TOKEN',
    'WEBHOOK_URL'
]

# Log presence of environment variables
for var_name in REQUIRED_ENV_VARS:
    logger.info(f"ENV_CHECK: {var_name} present: {var_name in os.environ}")

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    critical_message = f"CRITICAL STARTUP FAILURE: Missing required environment variables: {', '.join(missing_vars)}"
    logger.critical(critical_message)
    sys.exit(critical_message) # Exit if critical env vars are missing

# Get validated environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

# Validate Airtable API key format
if not TELEGRAM_BOT_TOKEN.startswith('pat'):
    critical_message = "CRITICAL STARTUP FAILURE: Invalid Airtable API key format. Must start with 'pat'."
    logger.critical(critical_message)
    sys.exit(critical_message)

# Initialize Airtable client
try:
    airtable_api = Api(TELEGRAM_BOT_TOKEN)
    airtable_base = airtable_api.base(projects_table.base_id) # Type: Base
    projects_table: Table = airtable_base.table('Ongoing projects')
    updates_table: Table = airtable_base.table('Updates')
    projects_table.all(max_records=1) # Test connection by attempting a harmless read
    logger.info("Successfully connected to Airtable and verified table access.")
except Exception as e:
    critical_message = f"CRITICAL STARTUP FAILURE: Failed to initialize Airtable client or access tables: {e}"
    logger.critical(critical_message, exc_info=True)
    sys.exit(critical_message)

# --- Constants for Conversation States & Callbacks ---
(
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED,
) = range(7) # States for new project conversation

(
    SELECT_PROJECT, UPDATE_PROGRESS, UPDATE_BLOCKERS,
) = range(7, 10) # States for update project conversation

STATUS_OPTIONS = ['Idea', 'MVP', 'Launched'] # Project status options

# Callback data prefixes - ensure they are distinct and descriptive
UPDATE_PROJECT_PREFIX = "updateproject_"
VIEW_PROJECT_PREFIX = "viewproject_"
SELECT_PROJECT_PREFIX = "selectproject_" # For selecting a project to update

# Max input lengths for validation
MAX_PROJECT_NAME_LENGTH = 1000
MAX_TAGLINE_LENGTH = 2500 # Increased slightly
MAX_PROBLEM_STATEMENT_LENGTH = 5500 # Increased slightly
MAX_TECH_STACK_LENGTH = 5000
MAX_GITHUB_LINK_LENGTH = 300 # Increased slightly
MAX_HELP_NEEDED_LENGTH = 7500 # Increased slightly
MAX_UPDATE_LENGTH = 9000 # Increased
MAX_BLOCKERS_LENGTH = 10000 # Increased

# --- Custom Exceptions ---
class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass

# --- Helper Functions ---
def validate_input_text(text: str, field_name: str, max_length: int, can_be_empty: bool = False) -> str:
    """Validates text input: checks for emptiness (if not allowed) and max length."""
    processed_text = text.strip() # Remove leading/trailing whitespace
    if not can_be_empty and not processed_text:
        raise ValidationError(f"{field_name} cannot be empty. Please provide some text.")
    if len(processed_text) > max_length:
        raise ValidationError(
            f"{field_name} is too long. Max {max_length} characters allowed, you entered {len(processed_text)}."
        )
    return processed_text # Return stripped text

# --- Telegram Bot Command and Webhook Setup ---
async def set_telegram_bot_commands(bot_instance: Application.bot_data) -> None: # Using Application.bot_data for Bot type
    """Sets the bot commands displayed in Telegram clients."""
    commands = [
        BotCommand("start", "🚀 Welcome & instructions"),
        BotCommand("newproject", "✨ Create a new project"),
        BotCommand("myprojects", "📂 View & manage your projects"),
        BotCommand("cancel", "❌ Cancel current operation"),
    ]
    try:
        await bot_instance.set_my_commands(commands)
        logger.info("Bot commands successfully set in Telegram.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}", exc_info=True)

async def set_telegram_webhook_with_bot_commands(bot_token_val: str, webhook_url_val: str, bot_instance: Application.bot_data) -> bool:
    """Sets the Telegram webhook and bot commands."""
    logger.info(f"Attempting to set webhook to: {webhook_url_val}")
    set_webhook_api_url = f"https://api.telegram.org/bot{bot_token_val}/setWebhook"
    payload = {
        "url": webhook_url_val,
        "allowed_updates": ["message", "callback_query"] # Specify desired updates
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(set_webhook_api_url, json=payload)
            resp.raise_for_status()
            response_data = resp.json()
            if response_data.get("ok"):
                logger.info(f"Successfully set webhook: {response_data.get('description', 'OK')}")
                await set_telegram_bot_commands(bot_instance) # Set commands after successful webhook
                return True
            else:
                logger.error(f"Telegram API error when setting webhook: {response_data}")
                return False
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError setting webhook: {e.response.status_code} - {e.response.text}", exc_info=True)
    except httpx.RequestError as e:
        logger.error(f"RequestError setting webhook (network issue?): {e}", exc_info=True)
    except Exception as e: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error setting webhook: {e}", exc_info=True)
    return False


# --- Handler Definitions (Command, Conversation, Callback) ---
# These would ideally be in separate files (e.g., handlers/command_handlers.py, handlers/conversation_handlers.py)


# General Error Handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates and inform the user if possible."""
    logger.error(f"GLOBAL_ERROR_HANDLER: Update {update} caused error: {context.error}", exc_info=context.error)
    if isinstance(update, Update):
        user_message = "🤖 Apologies, an unexpected error occurred. The team has been notified. Please try again later."
        if update.effective_message:
            try:
                await update.effective_message.reply_text(user_message)
            except Exception as e_reply:
                logger.error(f"Error sending error reply message: {e_reply}", exc_info=True)
        elif update.callback_query and update.effective_chat: # If error from callback, send new message
             try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=user_message)
             except Exception as e_send:
                logger.error(f"Error sending error message on callback error: {e_send}", exc_info=True)

# --- Command Handlers (Example: /start) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    if not update.effective_user: return # Should not happen with CommandHandler
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hello {user_name}!\n\n"
        "I'm your Project Tracker Bot for Loophole Hackers.\n\n"
        "Here's what I can do:\n"
        "  ✨ /newproject - Log a new project idea or ongoing work.\n"
        "  📂 /myprojects - View, update, or get details on your projects.\n"
        "  ❌ /cancel - Stop any current operation (like project creation).\n\n"
        "Let's get tracking! 🚀"
    )
    try:
        await update.message.reply_text(welcome_message, parse_mode='Markdown') # Assuming Markdown is fine
    except TelegramError as e:
        logger.error(f"Error sending /start message: {e}", exc_info=True)

# --- Placeholder for Conversation Handlers & Other Command Handlers ---
# You need to define or import these based on your bot's logic.
# For example: newproject_entry_point, project_name_state, my_projects_command, etc.

# This function wires up all your handlers to the PTB application.
# ** IMPORTANT: You MUST define or import all referenced handler functions **
def setup_all_bot_handlers(ptb_application: Application) -> None:
    """Adds all command, message, conversation, and callback handlers to the PTB Application."""
    from handlers.new_project import (
        newproject_entry_point, project_name_state, project_tagline_state,
        problem_statement_state, tech_stack_state, github_link_state,
        project_status_state_callback, help_needed_state, cancel_conversation
    )
    from handlers.update_project import (
        handle_project_action_callback, update_progress_state, update_blockers_state, select_project_for_update
    )
    from handlers.myprojects import my_projects_command
    from handlers.view_project import handle_project_action_callback as view_project_callback
    from constants import (
        PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED,
        SELECT_PROJECT, UPDATE_PROGRESS, UPDATE_BLOCKERS,
        STATUS_OPTIONS, UPDATE_PROJECT_PREFIX, VIEW_PROJECT_PREFIX, SELECT_PROJECT_PREFIX
    )
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters

    ptb_application.add_error_handler(error_handler)

    # New Project Conversation
    new_project_conv = ConversationHandler(
        entry_points=[CommandHandler('newproject', newproject_entry_point)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name_state)],
            PROJECT_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_tagline_state)],
            PROBLEM_STATEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, problem_statement_state)],
            TECH_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tech_stack_state)],
            GITHUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, github_link_state)],
            PROJECT_STATUS: [CallbackQueryHandler(project_status_state_callback)],
            HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_needed_state)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    ptb_application.add_handler(new_project_conv)

    # Update Project Conversation
    update_project_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_project_action_callback, pattern=f"^{UPDATE_PROJECT_PREFIX}"),
            CommandHandler('updateproject', handle_project_action_callback)
        ],
        states={
            SELECT_PROJECT: [CallbackQueryHandler(select_project_for_update, pattern=f"^{SELECT_PROJECT_PREFIX}")],
            UPDATE_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_progress_state)],
            UPDATE_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_blockers_state)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    ptb_application.add_handler(update_project_conv)

    # Simple Command Handlers
    ptb_application.add_handler(CommandHandler("start", start_command))
    ptb_application.add_handler(CommandHandler("myprojects", my_projects_command))

    # View Project Callback Handler
    ptb_application.add_handler(CallbackQueryHandler(view_project_callback, pattern=f"^{VIEW_PROJECT_PREFIX}"))

    logger.info("Bot handlers setup function called (all real handlers wired up).")


# --- Core Telegram Application Initialization (Lazy) ---
async def initialize_telegram_bot_instance_lazily() -> Optional[Application]:
    """
    Creates, configures, initializes, and returns a Telegram Application instance.
    Called lazily on the first request to a worker, within an async context.
    """
    worker_pid = os.getpid()
    logger.info(f"[Worker {worker_pid}] LAZY_INIT: Creating and initializing new Application instance.")

    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
        logger.error(f"[Worker {worker_pid}] LAZY_INIT: Missing TELEGRAM_BOT_TOKEN or WEBHOOK_URL. Cannot initialize.")
        return None

    try:
        temp_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: PTB Application object built: {temp_app}")

        setup_all_bot_handlers(temp_app) # Wire up all handlers
        
        await temp_app.initialize()
        ptb_initialized_flag = getattr(temp_app, '_initialized', False)
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: temp_app.initialize() completed. PTB _initialized: {ptb_initialized_flag}")

        if not ptb_initialized_flag:
            logger.error(f"[Worker {worker_pid}] LAZY_INIT: Application created but PTB _initialized flag is False after .initialize().")
            return None

        webhook_set_ok = await set_telegram_webhook_with_bot_commands(TELEGRAM_BOT_TOKEN, WEBHOOK_URL, temp_app.bot)
        if not webhook_set_ok:
            logger.warning(f"[Worker {worker_pid}] LAZY_INIT: Failed to set Telegram webhook during lazy init. Proceeding cautiously.")
            # Decide if this is fatal. For now, we'll let it proceed if PTB init was OK.

        if hasattr(temp_app, 'post_init') and callable(temp_app.post_init):
            logger.info(f"[Worker {worker_pid}] LAZY_INIT: Calling temp_app.post_init().")
            await temp_app.post_init()
            logger.info(f"[Worker {worker_pid}] LAZY_INIT: temp_app.post_init() completed.")
        else:
            post_init_attr_val = getattr(temp_app, 'post_init', 'ATTRIBUTE_NOT_FOUND')
            logger.warning(
                f"[Worker {worker_pid}] LAZY_INIT: temp_app.post_init is not callable or not found. "
                f"Type: {type(temp_app)}, Attribute Value: {post_init_attr_val}"
            )
        
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: New Application instance fully initialized and ready.")
        return temp_app

    except Exception as e:
        logger.critical(f"[Worker {worker_pid}] LAZY_INIT: CRITICAL error during Application instance initialization: {e}", exc_info=True)
        return None


# --- Flask Routes ---
@app.route('/', methods=['POST'])
async def telegram_webhook_route(): # Renamed to avoid clash with any other 'telegram_webhook'
    """Handles incoming updates from Telegram via webhook."""
    global application # To modify the global 'application' if needed

    current_app_for_request = application # Use current global state

    # Check if application needs initialization (is None or not PTB-initialized)
    if current_app_for_request is None or not getattr(current_app_for_request, '_initialized', False):
        async with application_lock: # Ensure only one greenlet/request initializes it per worker
            # Re-check after acquiring lock, as 'application' might have been set by another greenlet
            if application is None or not getattr(application, '_initialized', False):
                worker_pid = os.getpid()
                logger.info(f"[Worker {worker_pid}] WEBHOOK: Global 'application' NOT ready. Attempting LAZY initialization.")
                
                initialized_app_obj = await initialize_telegram_bot_instance_lazily()
                
                if initialized_app_obj and getattr(initialized_app_obj, '_initialized', False):
                    application = initialized_app_obj # Set the global 'application'
                    current_app_for_request = application # Use this new instance for current request
                    logger.info(f"[Worker {worker_pid}] WEBHOOK: Lazy initialization SUCCEEDED. Global 'application' is now set.")
                else:
                    logger.critical(f"[Worker {worker_pid}] WEBHOOK: Lazy initialization FAILED. Bot cannot process update.")
                    return jsonify({'error': 'Bot backend initialization failed'}), 500
            else:
                current_app_for_request = application # Use the one set by another greenlet
                logger.info(f"[Worker {os.getpid()}] WEBHOOK: Global 'application' was set by another request while this one awaited lock.")

    # Final check: current_app_for_request must be a valid, initialized Application object
    if current_app_for_request is None or not getattr(current_app_for_request, '_initialized', False):
        logger.critical(f"[Worker {os.getpid()}] WEBHOOK: CRITICAL - 'application' is STILL not ready before processing update. This should not happen.")
        return jsonify({'error': 'Bot backend critically uninitialized'}), 500
    
    # Process the update
    try:
        request_data = await request.get_json(force=True) # Use await for async Flask
        chat_id = request_data.get('message', {}).get('chat', {}).get('id') or \
                  request_data.get('callback_query', {}).get('message', {}).get('chat', {}).get('id')
        logger.info(f"WEBHOOK: Received update for chat_id: {chat_id if chat_id else 'Unknown'}")

        update_obj = Update.de_json(request_data, current_app_for_request.bot)
        await current_app_for_request.process_update(update_obj)
    except TelegramError as te: # Catch specific Telegram errors for better logging potentially
        logger.error(f"WEBHOOK: TelegramError processing update: {te}", exc_info=True)
        return jsonify({'status': 'telegram error processing update'}), 200
    except Exception as e:
        logger.error(f"WEBHOOK: Generic error processing update: {e}", exc_info=True)
        return jsonify({'status': 'general error processing update'}), 200
    
    return jsonify({'status': 'ok'}), 200


# --- Gunicorn Hooks (defined in app.py, referenced by gunicorn_config.py) ---
def on_worker_boot(worker_obj): # Gunicorn passes the worker object
    """Gunicorn hook called when a worker is started."""
    # With lazy initialization, this hook doesn't need to initialize 'application'.
    # It can be used for other synchronous worker-level setup.
    worker_pid = worker_obj.pid if worker_obj else os.getpid() # Gunicorn passes worker object
    logger.info(f"APP_HOOK: on_worker_boot for worker PID {worker_pid}. PTB Application will be initialized lazily on first request.")
    # Global 'application' remains None here.

def worker_int(worker_obj):
    """Gunicorn hook called for graceful shutdown (SIGINT, SIGQUIT)."""
    global application # Access the global application
    pid = worker_obj.pid if worker_obj else 'UnknownPID'
    logger.info(f"APP_HOOK: worker_int (graceful shutdown) for worker PID {pid}.")
    if application and hasattr(application, 'shutdown') and callable(application.shutdown):
        logger.info(f"APP_HOOK: Attempting graceful shutdown of PTB Application for worker PID {pid}.")
        try:
            asyncio.run(application.shutdown()) # PTB's shutdown is async
            logger.info(f"APP_HOOK: PTB Application for worker PID {pid} shut down successfully.")
        except RuntimeError as e: # Catch "Event loop is closed" if it happens here too
            if "Event loop is closed" in str(e):
                logger.warning(f"APP_HOOK: Event loop was already closed during shutdown for worker PID {pid}. {e}")
            else:
                logger.error(f"APP_HOOK: RuntimeError during PTB Application shutdown for worker PID {pid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"APP_HOOK: Generic error during PTB Application shutdown for worker PID {pid}: {e}", exc_info=True)
    else:
        logger.info(f"APP_HOOK: PTB Application not available or no shutdown method for worker PID {pid} during worker_int.")

def worker_abort(worker_obj):
    """Gunicorn hook called when a worker is aborted (e.g., timeout)."""
    # Similar to worker_int, attempt a shutdown.
    global application
    pid = worker_obj.pid if worker_obj else 'UnknownPID'
    logger.warning(f"APP_HOOK: worker_abort for worker PID {pid}.")
    if application and hasattr(application, 'shutdown') and callable(application.shutdown):
        logger.warning(f"APP_HOOK: Attempting shutdown of PTB Application for aborted worker PID {pid}.")
        try:
            asyncio.run(application.shutdown())
            logger.info(f"APP_HOOK: PTB Application (aborted worker PID {pid}) shutdown attempt completed.")
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                 logger.warning(f"APP_HOOK: Event loop was already closed during shutdown for aborted worker PID {pid}. {e}")
            else:
                logger.error(f"APP_HOOK: RuntimeError during PTB Application shutdown for aborted worker PID {pid}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"APP_HOOK: Generic error during PTB Application shutdown for aborted worker PID {pid}: {e}", exc_info=True)
    else:
        logger.info(f"APP_HOOK: PTB Application not available or no shutdown method for aborted worker PID {pid} during worker_abort.")

# --- Main Entry Point (for `python app.py`, not used by Gunicorn directly for serving) ---
if __name__ == '__main__':
    logger.info("Script executed with `if __name__ == '__main__':`. This is typically for local development or direct invocation, not for Gunicorn serving.")
    logger.info("For Gunicorn, ensure 'app:app' is the entry point and gunicorn_config.py is used via '-c'.")
    # Example: To run locally with Flask's dev server (less ideal for async, use Uvicorn or Hypercorn for better async local dev)
    # if os.getenv("FLASK_DEBUG"): # Or some other local run flag
    #    logger.info("Running Flask development server (not for production).")
    #    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=True)
    pass