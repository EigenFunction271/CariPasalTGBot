import os
import logging
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from pyairtable import Api, Table
# import requests # No longer needed for set_telegram_webhook
import httpx      # Import httpx
from datetime import datetime, timezone
import asyncio

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

logger.info("Environment Variables Check:")
logger.info(f"AIRTABLE_API_KEY present: {'AIRTABLE_API_KEY' in os.environ}")
logger.info(f"AIRTABLE_BASE_ID present: {'AIRTABLE_BASE_ID' in os.environ}")
logger.info(f"TELEGRAM_BOT_TOKEN present: {'TELEGRAM_BOT_TOKEN' in os.environ}")
logger.info(f"WEBHOOK_URL present: {'WEBHOOK_URL' in os.environ}")

# Create the Telegram Application object at the top level
# It will be initialized *per worker* to ensure proper context.
application: Optional[Application] = None

# Initialize Flask app
app = Flask(__name__)

# Health check endpoint
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

# Ping endpoint for keeping the service alive
@app.route('/ping')
def ping():
    return jsonify({
        'status': 'pong',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

# Telegram webhook endpoint
@app.route('/', methods=['POST'])
async def telegram_webhook():
    global application # Declare global to access the application object
    if application is None:
        logger.error("Telegram Application not initialized when webhook received. Attempting re-initialization (should not happen in normal operation).")
        # In a very rare race condition, or if a worker starts late, re-initialize
        # This is a fallback and indicates a potential issue with worker setup
        await initialize_telegram_bot_for_worker()
        if application is None:
            logger.critical("Failed to initialize Telegram Application even after re-attempt.")
            return 'Internal Server Error: Bot not ready', 500

    data = request.get_json(force=True)
    logger.info(f"Received webhook update for chat ID: {data.get('message', {}).get('chat', {}).get('id')}") # Log incoming updates with chat ID for better debugging
    
    update = Update.de_json(data, application.bot)
    try:
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        # It's good practice to return a 200 OK to Telegram even on internal processing errors
        # to prevent Telegram from retrying endlessly, unless the error is critical for webhook setup.
        # However, for debugging during development, returning 500 is helpful.
        return 'Error processing update', 200 # Changed to 200 for Telegram
    
    return 'ok', 200

# Validate required environment variables (keep this at the top level)
REQUIRED_ENV_VARS = [
    'TELEGRAM_BOT_TOKEN',
    'AIRTABLE_API_KEY',
    'AIRTABLE_BASE_ID',
    'WEBHOOK_URL'
]

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

# Validate Airtable token format (keep this at the top level)
airtable_token = os.getenv('AIRTABLE_API_KEY', '')
if not airtable_token.startswith('pat'):
    logger.error("Invalid Airtable token format. Personal Access Tokens should start with 'pat'")
    sys.exit(1)

# Initialize Airtable (keep this at the top level, as it's typically shared across workers)
try:
    airtable = Api(airtable_token)
    base = airtable.base(os.getenv('AIRTABLE_BASE_ID'))
    projects_table = base.table('Ongoing projects')
    updates_table = base.table('Updates')
    
    try:
        test_result = projects_table.all(limit=1)
        logger.info("Successfully connected to Airtable")
        logger.info(f"Found table: {projects_table.name}")
    except Exception as e:
        logger.error(f"Airtable connection test failed: {str(e)}")
        logger.error(f"API Key format: {airtable_token[:4]}...{airtable_token[-4:]}")
        logger.error(f"Base ID: {os.getenv('AIRTABLE_BASE_ID')}")
        raise
except Exception as e:
    logger.error(f"Failed to initialize Airtable: {e}")
    logger.error("Please check your AIRTABLE_API_KEY and AIRTABLE_BASE_ID environment variables")
    sys.exit(1)

# Conversation states and other constants (remain the same)
(
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED,
) = range(7)

(
    SELECT_PROJECT, UPDATE_PROGRESS, UPDATE_BLOCKERS,
) = range(7, 10)

STATUS_OPTIONS = ['Idea', 'MVP', 'Launched']
UPDATE_PREFIX = "update_"
VIEW_PREFIX = "view_"

MAX_PROJECT_NAME_LENGTH = 100
MAX_TAGLINE_LENGTH = 200
MAX_PROBLEM_STATEMENT_LENGTH = 1000
MAX_TECH_STACK_LENGTH = 500
MAX_HELP_NEEDED_LENGTH = 500
MAX_UPDATE_LENGTH = 1000
MAX_BLOCKERS_LENGTH = 500

class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass

def validate_input(text: str, field_name: str, max_length: int) -> None:
    if not text or not text.strip():
        raise ValidationError(f"{field_name} cannot be empty")
    if len(text) > max_length:
        raise ValidationError(f"{field_name} must be less than {max_length} characters")

# --- Async functions (remain the same, no need to duplicate) ---
async def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    # ... (same as before)
    try:
        formula = f"{{Owner Telegram ID}}='{user_id}'"
        return projects_table.all(formula=formula)
    except Exception as e:
        logger.error(f"Error fetching user projects: {e}")
        return []

async def get_project_updates(project_id: str) -> List[Dict[str, Any]]:
    # ... (same as before)
    try:
        formula = f"{{Project}}='{project_id}'"
        return updates_table.all(formula=formula, sort=[{"field": "Timestamp", "direction": "desc"}])
    except Exception as e:
        logger.error(f"Error fetching project updates: {e}")
        return []

async def format_project_summary(project: Dict[str, Any]) -> str:
    # ... (same as before)
    try:
        fields = project['fields']
        return (
            f"📋 *{fields['Project Name']}*\n"
            f"_{fields['One-liner']}_\n\n"
            f"*Status:* {fields['Status']}\n"
            f"*Stack:* {fields['Stack']}\n"
            f"*Help Needed:* {fields['Help Needed']}\n"
            f"*GitHub/Demo:* {fields['GitHub/Demo']}"
        )
    except KeyError as e:
        logger.error(f"Missing field in project data: {e}")
        return "Error: Project data is incomplete"

async def myprojects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (same as before)
    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        await update.message.reply_text(
            "You don't have any projects yet. Use /newproject to create one!"
        )
        return
    
    message = "Here are your projects:\n\n"
    for i, project in enumerate(projects, 1):
        message += f"{i}. {project['fields']['Project Name']}\n"
        message += f"   Status: {project['fields']['Status']}\n"
        message += f"   {project['fields']['One-liner']}\n\n"
    
    keyboard = []
    for project in projects:
        project_name = project['fields']['Project Name']
        project_id = project['id']
        keyboard.append([
            InlineKeyboardButton(
                f"📝 Update {project_name}",
                callback_data=f"{UPDATE_PREFIX}{project_id}"
            ),
            InlineKeyboardButton(
                f"👁 View {project_name}",
                callback_data=f"{VIEW_PREFIX}{project_id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_project_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith(UPDATE_PREFIX):
        project_id = callback_data[len(UPDATE_PREFIX):]
        projects = await get_user_projects(str(update.effective_user.id))
        selected_project = next((p for p in projects if p['id'] == project_id), None)
        
        if not selected_project:
            await query.edit_message_text(
                "❌ Error: Project not found. Please try /myprojects again."
            )
            return ConversationHandler.END
        
        context.user_data['selected_project_id'] = project_id
        context.user_data['selected_project'] = selected_project
        
        await query.edit_message_text(
            f"Updating: {selected_project['fields']['Project Name']}\n\n"
            "What progress have you made this week?"
        )
        return UPDATE_PROGRESS
    
    elif callback_data.startswith(VIEW_PREFIX):
        project_id = callback_data[len(VIEW_PREFIX):]
        projects = await get_user_projects(str(update.effective_user.id))
        selected_project = next((p for p in projects if p['id'] == project_id), None)
        
        if not selected_project:
            await query.edit_message_text(
                "❌ Error: Project not found. Please try /myprojects again."
            )
            return ConversationHandler.END
        
        updates = await get_project_updates(project_id)
        project_summary = await format_project_summary(selected_project)
        
        updates_text = "\n\n*Recent Updates:*\n"
        if updates:
            for update_record in updates[:3]:
                fields = update_record['fields']
                updates_text += f"\n📅 {fields.get('Timestamp', 'No date')}\n"
                updates_text += f"Progress: {fields.get('Update', 'No update')}\n"
                if fields.get('Blockers'):
                    updates_text += f"Blockers: {fields['Blockers']}\n"
        else:
            updates_text += "\nNo updates yet."
        
        keyboard = [[
            InlineKeyboardButton(
                "📝 Update Project",
                callback_data=f"{UPDATE_PREFIX}{project_id}"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{project_summary}{updates_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (same as before)
    try:
        welcome_message = (
            "👋 Welcome to the Loophole Hackers Project Tracker!\n\n"
            "I can help you track your project progress. Here are the available commands:\n\n"
            "/newproject - Create a new project\n"
            "/updateproject - Update an existing project\n"
            "/myprojects - View your projects"
        )
        await update.message.reply_text(welcome_message)
    except TelegramError as e:
        logger.error(f"Error sending welcome message: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )

async def newproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    try:
        await update.message.reply_text(
            "Let's create a new project! 🚀\n\n"
            "What's the name of your project?"
        )
        return PROJECT_NAME
    except TelegramError as e:
        logger.error(f"Error starting new project: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )
        return ConversationHandler.END

async def project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    try:
        validate_input(update.message.text, "Project name", MAX_PROJECT_NAME_LENGTH)
        context.user_data['project_name'] = update.message.text
        await update.message.reply_text(
            "Great! Now, give me a one-liner tagline for your project:"
        )
        return PROJECT_TAGLINE
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return PROJECT_NAME
    except TelegramError as e:
        logger.error(f"Error in project_name handler: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )
        return ConversationHandler.END

async def project_tagline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['tagline'] = update.message.text
    await update.message.reply_text(
        "What problem does your project solve? Please provide a brief problem statement:"
    )
    return PROBLEM_STATEMENT

async def problem_statement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['problem_statement'] = update.message.text
    await update.message.reply_text(
        "What technologies are you using? List your tech stack:"
    )
    return TECH_STACK

async def tech_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['tech_stack'] = update.message.text
    await update.message.reply_text(
        "Do you have a GitHub repository or demo link? Please share it:"
    )
    return GITHUB_LINK

async def github_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['github_link'] = update.message.text
    
    keyboard = [
        [InlineKeyboardButton(status, callback_data=status)]
        for status in STATUS_OPTIONS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "What's the current status of your project?",
        reply_markup=reply_markup
    )
    return PROJECT_STATUS

async def project_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    query = update.callback_query
    await query.answer()
    context.user_data['status'] = query.data
    
    await query.edit_message_text(
        "Finally, what kind of help do you need? (e.g., technical expertise, design, marketing)"
    )
    return HELP_NEEDED

async def help_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    try:
        validate_input(update.message.text, "Help needed", MAX_HELP_NEEDED_LENGTH)
        context.user_data['help_needed'] = update.message.text
        
        project_data = {
            'Project Name': context.user_data['project_name'],
            'Owner Telegram ID': str(update.effective_user.id),
            'One-liner': context.user_data['tagline'],
            'Problem Statement': context.user_data['problem_statement'],
            'Stack': context.user_data['tech_stack'],
            'GitHub/Demo': context.user_data['github_link'],
            'Status': context.user_data['status'],
            'Help Needed': context.user_data['help_needed'],
        }
        
        try:
            projects_table.create(project_data)
            
            await update.message.reply_text(
                "🎉 Your project has been created successfully!\n\n"
                "You can use /myprojects to view your projects or /updateproject to log progress."
            )
        except Exception as e:
            logger.error(f"Error saving project to Airtable: {e}")
            await update.message.reply_text(
                "❌ Sorry, there was an error saving your project. Please try again later."
            )
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return HELP_NEEDED
    except TelegramError as e:
        logger.error(f"Error in help_needed handler: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error in help_needed handler: {e}")
        await update.message.reply_text(
            "Sorry, an unexpected error occurred. Please try again later."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    await update.message.reply_text(
        "Project creation cancelled. Use /newproject to start again."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def updateproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        await update.message.reply_text(
            "You don't have any projects yet. Use /newproject to create one!"
        )
        return ConversationHandler.END
    
    context.user_data['projects'] = projects
    
    keyboard = [
        [InlineKeyboardButton(project['fields']['Project Name'], callback_data=project['id'])]
        for project in projects
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a project to update:",
        reply_markup=reply_markup
    )
    return SELECT_PROJECT

async def select_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_project_id'] = query.data
    
    selected_project = next(
        (p for p in context.user_data['projects'] if p['id'] == query.data),
        None
    )
    
    if not selected_project:
        await query.edit_message_text(
            "❌ Error: Project not found. Please try /updateproject again."
        )
        return ConversationHandler.END
    
    context.user_data['selected_project'] = selected_project
    
    await query.edit_message_text(
        f"Updating: {selected_project['fields']['Project Name']}\n\n"
        "What progress have you made this week?"
    )
    return UPDATE_PROGRESS

async def update_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['progress'] = update.message.text
    
    await update.message.reply_text(
        "Are there any blockers or challenges you're facing?"
    )
    return UPDATE_BLOCKERS

async def update_blockers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (same as before)
    context.user_data['blockers'] = update.message.text
    
    try:
        update_data = {
            'Project': [context.user_data['selected_project_id']],
            'Update': context.user_data['progress'],
            'Blockers': context.user_data['blockers'],
            'Updated By': str(update.effective_user.id),
        }
        
        updates_table.create(update_data)
        
        await update.message.reply_text(
            "✅ Your project update has been saved successfully!\n\n"
            "You can use /myprojects to view your projects or /updateproject to log another update."
        )
    except Exception as e:
        logger.error(f"Error saving update to Airtable: {e}")
        await update.message.reply_text(
            "❌ Sorry, there was an error saving your update. Please try again later."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (same as before)
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an error. Please try again later."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def setup_bot_handlers(app_instance: Application) -> None:
    # ... (same as before)
    app_instance.add_error_handler(error_handler)

    new_project_handler = ConversationHandler(
        entry_points=[CommandHandler('newproject', newproject)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name)],
            PROJECT_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_tagline)],
            PROBLEM_STATEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, problem_statement)],
            TECH_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tech_stack)],
            GITHUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, github_link)],
            PROJECT_STATUS: [CallbackQueryHandler(project_status)],
            HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_needed)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    update_project_handler = ConversationHandler(
        entry_points=[
            CommandHandler('updateproject', updateproject),
            CallbackQueryHandler(handle_project_callback, pattern=f"^{UPDATE_PREFIX}")
        ],
        states={
            SELECT_PROJECT: [CallbackQueryHandler(select_project)],
            UPDATE_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_progress)],
            UPDATE_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_blockers)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app_instance.add_handler(CommandHandler("start", start))
    app_instance.add_handler(new_project_handler)
    app_instance.add_handler(update_project_handler)
    app_instance.add_handler(CommandHandler("myprojects", myprojects))
    app_instance.add_handler(CallbackQueryHandler(handle_project_callback, pattern=f"^{VIEW_PREFIX}"))

async def set_telegram_webhook(bot_token: str, webhook_url: str) -> None:
    set_webhook_url_tg = f"https://api.telegram.org/bot{bot_token}/setWebhook" # Renamed variable to avoid clash if requests was used elsewhere
    logger.info(f"Attempting to set webhook to: {webhook_url}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(set_webhook_url_tg, data={"url": webhook_url})
            resp.raise_for_status()  # Raises an HTTPStatusError for 4xx/5xx responses
            logger.info(f"Set webhook response: {resp.status_code} - {resp.text}")
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to set webhook (HTTP Error): {e.response.status_code} - {e.response.text}",
            exc_info=True
        )
    except httpx.RequestError as e: # Covers other request issues like network errors
        logger.error(f"Failed to set webhook (Request Error): {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred while setting webhook: {e}", exc_info=True)

# --- NEW: Function to initialize the bot application per worker ---
async def initialize_telegram_bot_for_worker():
    global application
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')

    if not bot_token or not webhook_url:
        logger.error("TELEGRAM_BOT_TOKEN or WEBHOOK_URL not set; cannot initialize bot application.")
        return

    # POINT OF CREATION
    application = Application.builder().token(bot_token).build()
    
    setup_bot_handlers(application) # This call might be an issue if application isn't fully 'ready'
                                   # or if it modifies 'application' in a way that breaks post_init.

    await set_telegram_webhook(bot_token, webhook_url) # Now succeeding
    
    # POINT OF FAILURE
    if application and hasattr(application, 'post_init') and callable(application.post_init):
        await application.post_init()
        logger.info("Telegram Application is ready for webhooks in this worker after post_init.")
    else:
        logger.error(f"Application object or post_init is not correctly set up before calling post_init. Application: {application}, post_init: {getattr(application, 'post_init', 'Not Found')}")
        # This else block is new for debugging

        
# --- Gunicorn Worker Setup (Hook into Gunicorn's lifecycle) ---
def on_starting(server, worker):
    """
    Called just before the master process is ready to start receiving signals.
    """
    logger.info("Gunicorn master process starting.")

def on_reload(server):
    """
    Called when a server reload is detected.
    """
    logger.info("Gunicorn master process reloading.")

def worker_int(worker):
    """
    Called when a worker receives the INT signal (e.g., during graceful shutdown).
    """
    logger.info(f"Worker {worker.pid} received INT signal.")
    if application:
        # Properly shut down the Telegram Application's internal asyncio loop
        logger.info(f"Shutting down Telegram Application for worker {worker.pid}")
        asyncio.run(application.shutdown()) # Use asyncio.run for shutdown


def worker_exit(server, worker):
    """
    Called when a worker is about to exit.
    """
    logger.info(f"Worker {worker.pid} exiting.")
    # No need for shutdown here if worker_int handles it.

def worker_abort(worker):
    """
    Called when a worker is aborted.
    """
    logger.warning(f"Worker {worker.pid} aborted.")
    if application:
        logger.warning(f"Attempting to shut down Telegram Application due to worker abort {worker.pid}")
        try:
            asyncio.run(application.shutdown())
        except Exception as e:
            logger.error(f"Error during shutdown on worker abort: {e}")

def on_worker_boot(worker):
    """
    Called when a worker starts.
    This is the ideal place to initialize the Telegram Application object for each worker.
    """
    logger.info(f"Worker {worker.pid} booting up. Initializing Telegram Application.")
    # Run the asynchronous initialization for the bot within the worker's own event loop
    # This ensures each worker has its own, properly initialized Application instance.
    try:
        # Use a new event loop for this if one isn't already running, or get the current one.
        # Since gunicorn's gevent workers manage their own async context, this needs to be careful.
        # monkey.patch_all() from gevent makes asyncio use gevent's event loop.
        # So we can just run the coroutine directly.
        # However, for Application initialization, it's safer to ensure it runs correctly.
        # For simplicity with gevent, we'll try to run it.
        
        # If running with gevent, the event loop patching might already be done.
        # Directly await within the worker context is more suitable if it were a truly async start method.
        # For this hook, we use asyncio.run to ensure it completes.
        # This is a common pattern for initialization in gunicorn hooks.
        asyncio.run(initialize_telegram_bot_for_worker())
    except Exception as e:
        logger.critical(f"Failed to initialize Telegram Application in worker {worker.pid}: {e}", exc_info=True)
        # If initialization fails, the worker is likely unhealthy.
        # Consider raising an exception here to let Gunicorn restart the worker.
        raise # Re-raise to signal a worker failure

# --- Main entry point (unchanged from your previous good version) ---
def main() -> None:
    """Starts the Flask app and sets up the bot."""
    # With Gunicorn and on_worker_boot, you typically don't run app.run() here directly.
    # Gunicorn will manage the Flask app instance and call it via the 'app:app' entry point.
    # The setup of the bot now happens in on_worker_boot.
    logger.info("Main application process started. Gunicorn will manage workers.")
    # The Flask application will be served by Gunicorn.
    # We do NOT call app.run() here directly, as Gunicorn will handle it.
    pass # This function is now effectively a placeholder for when the script runs directly

if __name__ == '__main__':
    # This block is only executed when the script is run directly (e.g., `python app.py`).
    # For Gunicorn, the `on_worker_boot` hook handles initialization.
    # If you still want to run directly for local testing (without Gunicorn), you'd put app.run() here.
    # However, for production with Gunicorn, this should be minimal.
    logger.info("Script executed directly. This is typically for local development.")
    # If you want to test locally with 'python app.py' and have an async Flask app:
    # you'd likely use an async web server like uvicorn for local testing, e.g.:
    # uvicorn app:app --host 0.0.0.0 --port 5000
    # For now, let's keep it simple for Gunicorn production deployment.
    # If you uncomment `app.run()` here, make sure your Flask app is ready for it (e.g., debug mode)
    # and understand it bypasses Gunicorn's worker management.
    pass