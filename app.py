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
import requests
from datetime import datetime, timezone
# import asyncio # No longer needed directly in the webhook handler

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

# Debug logging for environment variables
logger.info("Environment Variables Check:")
logger.info(f"AIRTABLE_API_KEY present: {'AIRTABLE_API_KEY' in os.environ}")
logger.info(f"AIRTABLE_BASE_ID present: {'AIRTABLE_BASE_ID' in os.environ}")
logger.info(f"TELEGRAM_BOT_TOKEN present: {'TELEGRAM_BOT_TOKEN' in os.environ}")
logger.info(f"WEBHOOK_URL present: {'WEBHOOK_URL' in os.environ}")

# Create the Telegram Application object at the top level
# We will initialize it properly in main()
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
# This function must be async to await application.process_update
@app.route('/', methods=['POST'])
async def telegram_webhook():
    if application is None:
        logger.error("Telegram Application not initialized when webhook received.")
        return 'Internal Server Error: Bot not ready', 500
    
    # Get the JSON data from the request
    data = request.get_json(force=True)
    logger.info(f"Received webhook update: {data}") # Log incoming updates
    
    # Process the update
    update = Update.de_json(data, application.bot)
    try:
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return 'Error processing update', 500 # Return an error status
    
    return 'ok', 200

# Validate required environment variables
REQUIRED_ENV_VARS = [
    'TELEGRAM_BOT_TOKEN',
    'AIRTABLE_API_KEY',  # This will be a Personal Access Token
    'AIRTABLE_BASE_ID',
    'WEBHOOK_URL'
]

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

# Validate Airtable token format
airtable_token = os.getenv('AIRTABLE_API_KEY', '')
if not airtable_token.startswith('pat'):
    logger.error("Invalid Airtable token format. Personal Access Tokens should start with 'pat'")
    sys.exit(1)

# Initialize Airtable (kept outside main as it's a global dependency)
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

# Conversation states for new project
(
    PROJECT_NAME,
    PROJECT_TAGLINE,
    PROBLEM_STATEMENT,
    TECH_STACK,
    GITHUB_LINK,
    PROJECT_STATUS,
    HELP_NEEDED,
) = range(7)

# Conversation states for update project
(
    SELECT_PROJECT,
    UPDATE_PROGRESS,
    UPDATE_BLOCKERS,
) = range(7, 10)

# Project status options
STATUS_OPTIONS = ['Idea', 'MVP', 'Launched']

# Callback data prefixes
UPDATE_PREFIX = "update_"
VIEW_PREFIX = "view_"

# Input validation
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
    """Validate input text length and content."""
    if not text or not text.strip():
        raise ValidationError(f"{field_name} cannot be empty")
    if len(text) > max_length:
        raise ValidationError(f"{field_name} must be less than {max_length} characters")
    # Add more validation rules as needed

async def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    """Fetch all projects for a given user from Airtable."""
    try:
        formula = f"{{Owner Telegram ID}}='{user_id}'"
        return projects_table.all(formula=formula)
    except Exception as e:
        logger.error(f"Error fetching user projects: {e}")
        return []

async def get_project_updates(project_id: str) -> List[Dict[str, Any]]:
    """Fetch recent updates for a project from Airtable."""
    try:
        formula = f"{{Project}}='{project_id}'"
        return updates_table.all(formula=formula, sort=[{"field": "Timestamp", "direction": "desc"}])
    except Exception as e:
        logger.error(f"Error fetching project updates: {e}")
        return []

async def format_project_summary(project: Dict[str, Any]) -> str:
    """Format a project's summary for display."""
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
    """Show user's projects with inline buttons for updates."""
    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        await update.message.reply_text(
            "You don't have any projects yet. Use /newproject to create one!"
        )
        return
    
    # Create message with project summaries
    message = "Here are your projects:\n\n"
    for i, project in enumerate(projects, 1):
        message += f"{i}. {project['fields']['Project Name']}\n"
        message += f"   Status: {project['fields']['Status']}\n"
        message += f"   {project['fields']['One-liner']}\n\n"
    
    # Create inline keyboard with buttons for each project
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
    """Handle callback queries for project actions."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    if callback_data.startswith(UPDATE_PREFIX):
        # Handle update action
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
        # Handle view action
        project_id = callback_data[len(VIEW_PREFIX):]
        projects = await get_user_projects(str(update.effective_user.id))
        selected_project = next((p for p in projects if p['id'] == project_id), None)
        
        if not selected_project:
            await query.edit_message_text(
                "❌ Error: Project not found. Please try /myprojects again."
            )
            return ConversationHandler.END
        
        # Get project updates
        updates = await get_project_updates(project_id)
        
        # Format project details
        project_summary = await format_project_summary(selected_project)
        
        # Format updates
        updates_text = "\n\n*Recent Updates:*\n"
        if updates:
            for update_record in updates[:3]:  # Show last 3 updates
                fields = update_record['fields']
                updates_text += f"\n📅 {fields.get('Timestamp', 'No date')}\n"
                updates_text += f"Progress: {fields.get('Update', 'No update')}\n"
                if fields.get('Blockers'):
                    updates_text += f"Blockers: {fields['Blockers']}\n"
        else:
            updates_text += "\nNo updates yet."
        
        # Create keyboard for quick update
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
    """Send a message when the command /start is issued."""
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
    """Start the new project creation process."""
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
    """Store the project name and ask for tagline."""
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
    """Store the tagline and ask for problem statement."""
    context.user_data['tagline'] = update.message.text
    await update.message.reply_text(
        "What problem does your project solve? Please provide a brief problem statement:"
    )
    return PROBLEM_STATEMENT

async def problem_statement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the problem statement and ask for tech stack."""
    context.user_data['problem_statement'] = update.message.text
    await update.message.reply_text(
        "What technologies are you using? List your tech stack:"
    )
    return TECH_STACK

async def tech_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the tech stack and ask for GitHub/demo link."""
    context.user_data['tech_stack'] = update.message.text
    await update.message.reply_text(
        "Do you have a GitHub repository or demo link? Please share it:"
    )
    return GITHUB_LINK

async def github_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the GitHub/demo link and ask for project status."""
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
    """Store the project status and ask for help needed."""
    query = update.callback_query
    await query.answer()
    context.user_data['status'] = query.data
    
    await query.edit_message_text(
        "Finally, what kind of help do you need? (e.g., technical expertise, design, marketing)"
    )
    return HELP_NEEDED

async def help_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the help needed and save the project to Airtable."""
    try:
        validate_input(update.message.text, "Help needed", MAX_HELP_NEEDED_LENGTH)
        context.user_data['help_needed'] = update.message.text
        
        # Prepare project data
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
            # Save to Airtable
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
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text(
        "Project creation cancelled. Use /newproject to start again."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def updateproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the project update process."""
    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        await update.message.reply_text(
            "You don't have any projects yet. Use /newproject to create one!"
        )
        return ConversationHandler.END
    
    # Store projects in context for later use
    context.user_data['projects'] = projects
    
    # Create inline keyboard with project names
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
    """Handle project selection and ask for progress update."""
    query = update.callback_query
    await query.answer()
    
    # Store selected project ID
    context.user_data['selected_project_id'] = query.data
    
    # Find the selected project
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
    """Store progress update and ask for blockers."""
    context.user_data['progress'] = update.message.text
    
    await update.message.reply_text(
        "Are there any blockers or challenges you're facing?"
    )
    return UPDATE_BLOCKERS

async def update_blockers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store blockers and save the update to Airtable."""
    context.user_data['blockers'] = update.message.text
    
    try:
        # Prepare update data
        update_data = {
            'Project': [context.user_data['selected_project_id']],
            'Update': context.user_data['progress'],
            'Blockers': context.user_data['blockers'],
            'Updated By': str(update.effective_user.id),
        }
        
        # Save to Airtable
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
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an error. Please try again later."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def setup_bot_handlers(app_instance: Application) -> None:
    """Sets up all bot handlers for the given Application instance."""
    # Add error handler
    app_instance.add_error_handler(error_handler)

    # Add conversation handler for new project
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

    # Add conversation handler for update project
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

    # Add handlers
    app_instance.add_handler(CommandHandler("start", start))
    app_instance.add_handler(new_project_handler)
    app_instance.add_handler(update_project_handler)
    app_instance.add_handler(CommandHandler("myprojects", myprojects))
    app_instance.add_handler(CallbackQueryHandler(handle_project_callback, pattern=f"^{VIEW_PREFIX}"))

async def set_telegram_webhook(bot_token: str, webhook_url: str) -> None:
    """Sets the Telegram webhook."""
    set_webhook_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    try:
        resp = requests.post(set_webhook_url, data={"url": webhook_url})
        resp.raise_for_status() # Raise an exception for bad status codes
        logger.info(f"Set webhook response: {resp.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to set webhook: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while setting webhook: {e}")

async def run_bot_application():
    """Initializes and runs the Telegram bot application."""
    global application # Declare global to modify the top-level application variable
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')

    if not bot_token or not webhook_url:
        logger.error("TELEGRAM_BOT_TOKEN or WEBHOOK_URL not set; cannot initialize bot application.")
        sys.exit(1)

    # Initialize the Application properly
    application = Application.builder().token(bot_token).build()
    
    # Set up handlers
    setup_bot_handlers(application)

    # Set the webhook
    await set_telegram_webhook(bot_token, webhook_url)
    
    # Start the application in webhook mode
    # This prepares the application to process updates, but Flask handles the HTTP server part.
    await application.post_init() # Call post_init to finalize setup
    logger.info("Telegram Application is ready for webhooks.")


def main() -> None:
    """Starts the Flask app and sets up the bot."""
    try:
        # Run the bot application setup in an asyncio loop
        # This will initialize the Application and set the webhook
        import asyncio
        asyncio.run(run_bot_application())
        
        # Start Flask app - it will now handle incoming webhooks
        # Note: If running Flask with Gunicorn or similar, ensure it's configured
        # to support async functions for the webhook endpoint (e.g., using a gevent worker).
        # For simple 'flask run', it might require additional setup for async.
        logger.info("Starting Flask application.")
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    except Exception as e:
        logger.error(f"Error starting main process: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()