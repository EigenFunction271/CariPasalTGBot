# app.py
import os
import logging
import sys
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from flask import Flask, request, jsonify # Standard Flask imports
from telegram import Update, BotCommand # Telegram imports
from telegram.error import TelegramError # Specific error for handling
from telegram.ext import (
    Application,
    ContextTypes, # For type hinting context
    # Import specific handlers from telegram.ext inside setup_all_bot_handlers
    # as they are only used there, to keep top-level imports cleaner.
)
import httpx # Modern HTTP client, used by PTB and for direct calls
from datetime import datetime, timezone # For timestamps
import asyncio # For async operations and Lock

# Modularized imports
from constants import (
    logger, # Using logger from constants.py
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK,
    GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED, SELECT_PROJECT, UPDATE_PROGRESS,
    UPDATE_BLOCKERS, STATUS_OPTIONS, UPDATE_PROJECT_PREFIX, VIEW_PROJECT_PREFIX,
    SELECT_PROJECT_PREFIX
)
from database import ( # These are already async as per your database.py
    projects_table, updates_table, get_user_projects_from_airtable,
    get_project_updates_from_airtable, format_project_summary_text
)
# Assuming your handlers are structured correctly in the 'handlers' directory
from handlers.new_project import (
    newproject_entry_point, project_name_state, project_tagline_state,
    problem_statement_state, tech_stack_state, github_link_state,
    project_status_state_callback, help_needed_state, cancel_conversation
)
from handlers.update_project import (
    handle_project_action_callback as update_project_action_callback, # Renamed to avoid clash
    update_progress_state, update_blockers_state,
    select_project_for_update
)
from handlers.myprojects import my_projects_command
from handlers.view_project import handle_project_action_callback as view_project_action_callback


# --- Global Variables ---
application: Optional[Application] = None
application_lock = asyncio.Lock()

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Environment Variable Validation (Essential for app to run) ---
load_dotenv()
logger.info("Attempted to load environment variables from .env file.")

REQUIRED_APP_ENV_VARS = ['TELEGRAM_BOT_TOKEN', 'WEBHOOK_URL']
# Airtable specific vars are checked in database.py

for var_name in REQUIRED_APP_ENV_VARS:
    logger.info(f"APP_ENV_CHECK: {var_name} present: {var_name in os.environ}")

missing_app_vars = [var for var in REQUIRED_APP_ENV_VARS if not os.getenv(var)]
if missing_app_vars:
    critical_msg = f"CRITICAL STARTUP FAILURE (app.py): Missing  {', '.join(missing_app_vars)}"
    logger.critical(critical_msg)
    sys.exit(critical_msg)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')


# --- Telegram Bot Setup Functions ---
async def set_telegram_bot_commands(bot_instance: Application.bot_data) -> None:
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
    logger.info(f"Attempting to set webhook to: {webhook_url_val}")
    set_webhook_api_url = f"https://api.telegram.org/bot{bot_token_val}/setWebhook"
    payload = {"url": webhook_url_val, "allowed_updates": ["message", "callback_query"]}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(set_webhook_api_url, json=payload)
            resp.raise_for_status()
            response_data = resp.json()
            if response_data.get("ok"):
                logger.info(f"Successfully set webhook: {response_data.get('description', 'OK')}")
                await set_telegram_bot_commands(bot_instance)
                return True
            else:
                logger.error(f"Telegram API error setting webhook: {response_data}")
                return False
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPStatusError setting webhook: {e.response.status_code} - {e.response.text}", exc_info=True)
    except httpx.RequestError as e:
        logger.error(f"RequestError setting webhook: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error setting webhook: {e}", exc_info=True)
    return False

# --- General Error Handler for PTB ---
async def ptb_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"GLOBAL_PTB_ERROR_HANDLER: Update {update} caused error: {context.error}", exc_info=context.error)
    if isinstance(update, Update):
        user_message = "🤖 Apologies, an unexpected error occurred. Please try again."
        if update.effective_message:
            try: await update.effective_message.reply_text(user_message)
            except Exception as e: logger.error(f"Error sending error reply: {e}", exc_info=True)
        elif update.callback_query and update.effective_chat:
             try: await context.bot.send_message(chat_id=update.effective_chat.id, text=user_message)
             except Exception as e: logger.error(f"Error sending callback error message: {e}", exc_info=True)

# --- Command Handler: /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message: return
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hello {user_name}!\n\n"
        "I'm your Project Tracker Bot.\n\n"
        "Commands:\n"
        "  ✨ /newproject - Log a new project.\n"
        "  📂 /myprojects - View & manage your projects.\n"
        "  ❌ /cancel - Stop current operation.\n\n"
        "Let's track! 🚀"
    )
    try:
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    except TelegramError as e:
        logger.error(f"Error sending /start message: {e}", exc_info=True)

# --- Setup All Bot Handlers ---
def setup_all_bot_handlers(ptb_application: Application) -> None:
    # Import PTB handler types here to keep top-level cleaner
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters

    ptb_application.add_error_handler(ptb_error_handler)

    # New Project Conversation
    new_project_conv = ConversationHandler(
        entry_points=[CommandHandler('newproject', newproject_entry_point)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name_state)],
            PROJECT_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_tagline_state)],
            PROBLEM_STATEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, problem_statement_state)],
            TECH_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tech_stack_state)],
            GITHUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, github_link_state)],
            PROJECT_STATUS: [CallbackQueryHandler(project_status_state_callback, pattern=f"^({'|'.join(STATUS_OPTIONS)})$")], # Ensure pattern matches STATUS_OPTIONS
            HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_needed_state)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    ptb_application.add_handler(new_project_conv)

    # Update Project Conversation
    update_project_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(update_project_action_callback, pattern=f"^{UPDATE_PROJECT_PREFIX}"), # This handles the "Update" buttons
            CommandHandler('updateproject', my_projects_command) # Direct /updateproject to show project list
        ],
        states={
            # State for selecting a project if update_project_action_callback leads here
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

    # Standalone CallbackQueryHandler for "View Project" buttons from /myprojects
    ptb_application.add_handler(CallbackQueryHandler(view_project_action_callback, pattern=f"^{VIEW_PROJECT_PREFIX}"))

    logger.info("All PTB handlers have been configured.")

# --- Core Telegram Application Initialization (Lazy) ---
async def initialize_telegram_bot_instance_lazily() -> Optional[Application]:
    worker_pid = os.getpid()
    logger.info(f"[Worker {worker_pid}] LAZY_INIT: Creating and initializing new Application instance.")

    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL: # Already checked globally, but good for sanity
        logger.error(f"[Worker {worker_pid}] LAZY_INIT: Missing TELEGRAM_BOT_TOKEN or WEBHOOK_URL in lazy init path.")
        return None

    try:
        temp_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: PTB Application object built.")

        setup_all_bot_handlers(temp_app) # Wire up all handlers
        
        await temp_app.initialize()
        ptb_initialized_flag = getattr(temp_app, '_initialized', False)
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: temp_app.initialize() completed. PTB _initialized: {ptb_initialized_flag}")

        if not ptb_initialized_flag:
            logger.error(f"[Worker {worker_pid}] LAZY_INIT: PTB _initialized flag is False after .initialize(). Cannot proceed.")
            return None

        webhook_set_ok = await set_telegram_webhook_with_bot_commands(TELEGRAM_BOT_TOKEN, WEBHOOK_URL, temp_app.bot)
        if not webhook_set_ok: # Log warning but proceed if PTB part is okay. Webhook might be already set.
            logger.warning(f"[Worker {worker_pid}] LAZY_INIT: Call to set Telegram webhook indicated an issue (see previous logs).")

        if hasattr(temp_app, 'post_init') and callable(temp_app.post_init):
            logger.info(f"[Worker {worker_pid}] LAZY_INIT: Calling temp_app.post_init().")
            await temp_app.post_init()
            logger.info(f"[Worker {worker_pid}] LAZY_INIT: temp_app.post_init() completed.")
        else:
            post_init_val = getattr(temp_app, 'post_init', 'ATTRIBUTE_NOT_FOUND')
            logger.warning(
                f"[Worker {worker_pid}] LAZY_INIT: temp_app.post_init is not callable or not found. "
                f"Value: {post_init_val}" # Check if this still logs 'None'
            )
        
        logger.info(f"[Worker {worker_pid}] LAZY_INIT: New Application instance appears fully initialized.")
        return temp_app
    except Exception as e:
        logger.critical(f"[Worker {worker_pid}] LAZY_INIT: CRITICAL error during Application instance initialization: {e}", exc_info=True)
        return None

# --- Flask Routes ---
@app.route('/', methods=['POST'])
async def telegram_webhook_route():
    global application
    current_app_for_request = application

    if current_app_for_request is None or not getattr(current_app_for_request, '_initialized', False):
        async with application_lock:
            if application is None or not getattr(application, '_initialized', False): # Double-check lock
                worker_pid = os.getpid()
                logger.info(f"[Worker {worker_pid}] WEBHOOK: Global 'application' NOT ready. LAZY INIT attempt.")
                initialized_app_obj = await initialize_telegram_bot_instance_lazily()
                if initialized_app_obj and getattr(initialized_app_obj, '_initialized', False):
                    application = initialized_app_obj
                    current_app_for_request = application
                    logger.info(f"[Worker {worker_pid}] WEBHOOK: Lazy initialization SUCCEEDED.")
                else:
                    logger.critical(f"[Worker {worker_pid}] WEBHOOK: Lazy initialization FAILED.")
                    return jsonify({'error': 'Bot backend init failed'}), 500
            else:
                current_app_for_request = application
                logger.info(f"[Worker {os.getpid()}] WEBHOOK: App was set by another request during lock.")

    if current_app_for_request is None or not getattr(current_app_for_request, '_initialized', False):
        logger.critical(f"[Worker {os.getpid()}] WEBHOOK: CRITICAL - App STILL not ready.")
        return jsonify({'error': 'Bot backend critically uninitialized'}), 500
    
    try:
        # --- CORRECTED LINE ---
        request_data = request.get_json(force=True) # Synchronous call
        # --- ---

        chat_id_log = request_data.get('message', {}).get('chat', {}).get('id') or \
                      request_data.get('callback_query', {}).get('message', {}).get('chat', {}).get('id')
        logger.info(f"WEBHOOK: Received update for chat_id: {chat_id_log if chat_id_log else 'Unknown'}")

        update_obj = Update.de_json(request_data, current_app_for_request.bot)
        await current_app_for_request.process_update(update_obj)
    except TelegramError as te:
        logger.error(f"WEBHOOK: TelegramError processing update: {te}", exc_info=True)
        return jsonify({'status': 'telegram error processing update'}), 200
    except Exception as e: # Catch other errors like the TypeError if await was still there
        logger.error(f"WEBHOOK: Generic error processing update: {e}", exc_info=True) # Log the actual error type
        return jsonify({'status': f'general error processing update: {type(e).__name__}'}), 200
    
    return jsonify({'status': 'ok'}), 200

# --- Gunicorn Hooks (defined in app.py, referenced by gunicorn_config.py) ---
def on_worker_boot(worker_obj):
    worker_pid = worker_obj.pid if worker_obj else os.getpid()
    logger.info(f"APP_HOOK: on_worker_boot for worker PID {worker_pid}. PTB App will be lazy-initialized.")

def worker_int(worker_obj):
    global application
    pid = worker_obj.pid if worker_obj else 'UnknownPID'
    logger.info(f"APP_HOOK: worker_int (graceful shutdown) for worker PID {pid}.")
    if application and hasattr(application, 'shutdown') and callable(application.shutdown):
        logger.info(f"APP_HOOK: Attempting graceful shutdown of PTB App for worker PID {pid}.")
        try: asyncio.run(application.shutdown())
        except Exception as e: logger.error(f"APP_HOOK: Error during PTB shutdown (worker_int) for PID {pid}: {e}", exc_info=True)
    else: logger.info(f"APP_HOOK: PTB App not available for shutdown (worker_int) for PID {pid}.")

def worker_abort(worker_obj):
    global application
    pid = worker_obj.pid if worker_obj else 'UnknownPID'
    logger.warning(f"APP_HOOK: worker_abort for worker PID {pid}.")
    if application and hasattr(application, 'shutdown') and callable(application.shutdown):
        logger.warning(f"APP_HOOK: Attempting shutdown of PTB App for aborted worker PID {pid}.")
        try: asyncio.run(application.shutdown())
        except Exception as e: logger.error(f"APP_HOOK: Error during PTB shutdown (worker_abort) for PID {pid}: {e}", exc_info=True)
    else: logger.info(f"APP_HOOK: PTB App not available for shutdown (worker_abort) for PID {pid}.")

# --- Main Entry Point (for `python app.py`) ---
if __name__ == '__main__':
    logger.info("Script executed with `if __name__ == '__main__':` (typically for local dev).")
    # For Gunicorn, 'app:app' is entry point, and gunicorn_config.py is used via '-c'.
    # If FLASK_DEBUG or a similar env var is set, you might run app.run() here for local testing.
    # e.g., app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=True)
    pass