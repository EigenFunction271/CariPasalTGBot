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
import httpx
from datetime import datetime, timezone
import asyncio

# Configure logging (ensure it's set up before any logging calls)
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
    global application # Declare global to access/modify the application object
    
    current_app_instance = application # Capture current global state to work with

    if current_app_instance is None:
        logger.error("Telegram Application not available when webhook received. Attempting re-initialization.")
        try:
            # This call will set the global 'application' if successful
            await initialize_telegram_bot_for_worker()
            current_app_instance = application # Re-fetch the global application instance
            if current_app_instance is None: # Still None after attempt
                logger.critical("Failed to initialize Telegram Application even after re-attempt in webhook handler.")
                return 'Internal Server Error: Bot not ready', 500
            logger.info("Telegram Application re-initialized successfully in webhook handler.")
        except Exception as e:
            logger.critical(f"Exception during re-initialization in webhook handler: {e}", exc_info=True)
            return 'Internal Server Error: Bot initialization failed', 500

    data = request.get_json(force=True)
    # Log incoming updates with chat ID for better debugging (ensure data structure before accessing)
    chat_id = data.get('message', {}).get('chat', {}).get('id') or \
              data.get('callback_query', {}).get('message', {}).get('chat', {}).get('id')
    if chat_id:
        logger.info(f"Received webhook update for chat ID: {chat_id}")
    else:
        logger.info("Received webhook update (chat ID not found in common paths).")
    
    update = Update.de_json(data, current_app_instance.bot)
    try:
        await current_app_instance.process_update(update)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return 'Error processing update', 200 # Return 200 OK to Telegram
    
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
    logger.critical(f"Missing required environment variables: {', '.join(missing_vars)}") # Changed to critical
    sys.exit(1)

airtable_token = os.getenv('AIRTABLE_API_KEY', '')
if not airtable_token.startswith('pat'):
    logger.critical("Invalid Airtable token format. Personal Access Tokens should start with 'pat'") # Changed to critical
    sys.exit(1)

try:
    airtable = Api(airtable_token)
    base = airtable.base(os.getenv('AIRTABLE_BASE_ID'))
    projects_table = base.table('Ongoing projects')
    updates_table = base.table('Updates')
    projects_table.all(limit=1) # Test connection
    logger.info("Successfully connected to Airtable and accessed tables.")
except Exception as e:
    logger.critical(f"Failed to initialize Airtable: {e}", exc_info=True) # Changed to critical
    sys.exit(1)


# Conversation states and other constants
(
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED,
) = range(7)
(
    SELECT_PROJECT, UPDATE_PROGRESS, UPDATE_BLOCKERS,
) = range(7, 10)
STATUS_OPTIONS = ['Idea', 'MVP', 'Launched']
UPDATE_PREFIX = "update_"
VIEW_PREFIX = "view_"
MAX_PROJECT_NAME_LENGTH = 100 # Define other MAX lengths as in original code


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
    try:
        formula = f"{{Owner Telegram ID}}='{user_id}'"
        return projects_table.all(formula=formula)
    except Exception as e:
        logger.error(f"Error fetching user projects for {user_id}: {e}", exc_info=True)
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
    try:
        fields = project['fields']
        # Ensure all fields used here are checked or have defaults if they can be missing
        return (
            f"📋 *{fields.get('Project Name', 'N/A')}*\n"
            f"_{fields.get('One-liner', 'No tagline')}_\n\n"
            f"*Status:* {fields.get('Status', 'N/A')}\n"
            f"*Stack:* {fields.get('Stack', 'N/A')}\n"
            f"*Help Needed:* {fields.get('Help Needed', 'N/A')}\n"
            f"*GitHub/Demo:* {fields.get('GitHub/Demo', 'N/A')}"
        )
    except KeyError as e:
        logger.error(f"Missing field in project data for formatting summary: {e}")
        return "Error: Project data is incomplete for summary."
    except Exception as e:
        logger.error(f"Unexpected error formatting project summary: {e}", exc_info=True)
        return "Error displaying project summary."


async def myprojects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        logger.warning("myprojects: update.effective_user is None.")
        await update.message.reply_text("Could not identify user.")
        return
    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        await update.message.reply_text(
            "You don't have any projects yet. Use /newproject to create one!"
        )
        return
    
    message_parts = ["Here are your projects:\n"]
    keyboard_rows = []
    
    for i, project_record in enumerate(projects, 1):
        try:
            project_fields = project_record['fields']
            project_id = project_record['id']
            project_name = project_fields.get('Project Name', f"Unnamed Project {project_id}")
            
            message_parts.append(f"\n*{i}. {project_name}*")
            if 'Status' in project_fields:
                message_parts.append(f"   _Status:_ {project_fields['Status']}")
            if 'One-liner' in project_fields:
                message_parts.append(f"   _{project_fields['One-liner']}_")
            
            keyboard_rows.append([
                InlineKeyboardButton(
                    f"📝 Update {project_name[:30]}...", # Truncate for button
                    callback_data=f"{UPDATE_PREFIX}{project_id}"
                ),
                InlineKeyboardButton(
                    f"👁 View {project_name[:30]}...", # Truncate for button
                    callback_data=f"{VIEW_PREFIX}{project_id}"
                )
            ])
        except KeyError as e:
            logger.error(f"Missing field in project record {project_record.get('id', 'Unknown ID')} for myprojects: {e}")
            message_parts.append(f"\n{i}. Error displaying project (data incomplete)")
        except Exception as e:
            logger.error(f"Unexpected error processing project {project_record.get('id', 'Unknown ID')} in myprojects: {e}", exc_info=True)
            message_parts.append(f"\n{i}. Error displaying project.")

    message = "\n".join(message_parts)
    if not keyboard_rows: # Should not happen if projects exist, but as a safeguard
        await update.message.reply_text(message if len(message_parts) > 1 else "No projects found or error displaying projects.")
        return

    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_project_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]: # Return type can be int or None
    query = update.callback_query
    if not query:
        logger.warning("handle_project_callback: query is None.")
        return ConversationHandler.END # Or handle error appropriately
    await query.answer()
    
    callback_data = query.data
    if not update.effective_user:
        logger.warning("handle_project_callback: update.effective_user is None.")
        await query.edit_message_text("Error: Could not identify user.")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)

    if callback_data.startswith(UPDATE_PREFIX):
        project_id = callback_data[len(UPDATE_PREFIX):]
        projects = await get_user_projects(user_id) # Fetch projects for the current user
        selected_project = next((p for p in projects if p['id'] == project_id), None)
        
        if not selected_project:
            await query.edit_message_text(
                "❌ Error: Project not found or you don't have access. Please try /myprojects again."
            )
            return ConversationHandler.END
        
        context.user_data['selected_project_id'] = project_id
        context.user_data['selected_project'] = selected_project # Store the whole project record
        project_name = selected_project.get('fields', {}).get('Project Name', 'the selected project')

        await query.edit_message_text(
            f"Updating: *{project_name}*\n\n"
            "What progress have you made this week?",
            parse_mode='Markdown'
        )
        return UPDATE_PROGRESS # Next state in conversation
    
    elif callback_data.startswith(VIEW_PREFIX):
        project_id = callback_data[len(VIEW_PREFIX):]
        projects = await get_user_projects(user_id) # Fetch projects for the current user
        selected_project = next((p for p in projects if p['id'] == project_id), None)
        
        if not selected_project:
            await query.edit_message_text(
                "❌ Error: Project not found or you don't have access. Please try /myprojects again."
            )
            return ConversationHandler.END # End conversation
        
        project_summary = await format_project_summary(selected_project)
        updates = await get_project_updates(project_id) # project_id is link to 'Ongoing projects'
        
        updates_text_parts = ["\n\n*Recent Updates:*"]
        if updates:
            for i, update_record in enumerate(updates[:3]): # Show top 3 recent
                fields = update_record.get('fields', {})
                timestamp_str = fields.get('Timestamp', 'No date')
                try: # Try to parse and format timestamp if it's ISO format
                    dt_obj = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    formatted_date = dt_obj.strftime('%Y-%m-%d')
                except ValueError:
                    formatted_date = timestamp_str # Keep as is if not parsable
                except TypeError: # If timestamp_str is not a string
                     formatted_date = "Invalid date format"


                updates_text_parts.append(f"\n📅 _{formatted_date}_")
                updates_text_parts.append(f"  ↪️ {fields.get('Update', '_No progress detail_')}")
                if fields.get('Blockers'):
                    updates_text_parts.append(f"  ⚠️ Blockers: {fields['Blockers']}")
        else:
            updates_text_parts.append("\n_No updates recorded yet for this project._")
        
        updates_text = "\n".join(updates_text_parts)
        
        keyboard = [[
            InlineKeyboardButton(
                "📝 Update This Project", # More specific
                callback_data=f"{UPDATE_PREFIX}{project_id}" # Correct prefix for update
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{project_summary}{updates_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END # End conversation after viewing

    logger.warning(f"Unhandled callback_data in handle_project_callback: {callback_data}")
    await query.edit_message_text("Sorry, I didn't understand that action.")
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        welcome_message = (
            "👋 Welcome to the Loophole Hackers Project Tracker!\n\n"
            "I can help you track your project progress. Here are the available commands:\n\n"
            "/newproject - Create a new project\n"
            # /updateproject is now part of /myprojects flow primarily
            "/myprojects - View and update your projects"
        )
        if update.message:
             await update.message.reply_text(welcome_message)
        else:
            logger.warning("start command received without a message object.")
    except TelegramError as e:
        logger.error(f"Error sending welcome message: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text("Sorry, I encountered an error. Please try again later.")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in start handler: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text("An unexpected error occurred. Please try again.")


async def newproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message:
            await update.message.reply_text(
                "Let's create a new project! 🚀\n\n"
                "What's the name of your project?"
            )
            return PROJECT_NAME
        else: # Should not happen for a CommandHandler
            logger.warning("newproject command received without a message object.")
            return ConversationHandler.END
    except TelegramError as e:
        logger.error(f"Error starting new project: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text("Sorry, I encountered an error starting. Please try again later.")
        return ConversationHandler.END
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error in newproject handler: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text("An unexpected error occurred. Please try again.")
        return ConversationHandler.END


async def project_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please provide a project name.")
            return PROJECT_NAME
        validate_input(update.message.text, "Project name", MAX_PROJECT_NAME_LENGTH) # Assuming MAX_PROJECT_NAME_LENGTH is defined
        context.user_data['project_name'] = update.message.text
        await update.message.reply_text(
            "Great! Now, give me a one-liner tagline for your project (max 200 characters):"
        )
        return PROJECT_TAGLINE
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return PROJECT_NAME # Stay in the same state
    except TelegramError as e:
        logger.error(f"TelegramError in project_name handler: {e}", exc_info=True)
        await update.message.reply_text("Sorry, a communication error occurred. Please try sending the name again.")
        return PROJECT_NAME # Or ConversationHandler.END if preferred
    except Exception as e:
        logger.error(f"Unexpected error in project_name handler: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred. Please try again.")
        return ConversationHandler.END


async def project_tagline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text: # Basic check
            await update.message.reply_text("Please provide a tagline.")
            return PROJECT_TAGLINE
        validate_input(update.message.text, "Project tagline", MAX_TAGLINE_LENGTH) # Define MAX_TAGLINE_LENGTH
        context.user_data['tagline'] = update.message.text
        await update.message.reply_text(
            "What problem does your project solve? Please provide a brief problem statement (max 1000 characters):"
        )
        return PROBLEM_STATEMENT
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return PROJECT_TAGLINE
    except Exception as e: # General error handling
        logger.error(f"Error in project_tagline: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

async def problem_statement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please provide a problem statement.")
            return PROBLEM_STATEMENT
        validate_input(update.message.text, "Problem statement", MAX_PROBLEM_STATEMENT_LENGTH) # Define MAX_PROBLEM_STATEMENT_LENGTH
        context.user_data['problem_statement'] = update.message.text
        await update.message.reply_text(
            "What technologies are you using? List your tech stack (e.g., Python, React, AWS - max 500 characters):"
        )
        return TECH_STACK
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return PROBLEM_STATEMENT
    except Exception as e:
        logger.error(f"Error in problem_statement: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

async def tech_stack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please list your tech stack.")
            return TECH_STACK
        validate_input(update.message.text, "Tech stack", MAX_TECH_STACK_LENGTH) # Define MAX_TECH_STACK_LENGTH
        context.user_data['tech_stack'] = update.message.text
        await update.message.reply_text(
            "Do you have a GitHub repository or demo link? Please share it (or type 'none'):"
        )
        return GITHUB_LINK
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return TECH_STACK
    except Exception as e:
        logger.error(f"Error in tech_stack: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

async def github_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text: # Check message text exists
             # If you want to allow empty, handle 'none' specifically or remove validation for emptiness
            await update.message.reply_text("Please provide a GitHub/Demo link or type 'none'.")
            return GITHUB_LINK
        
        link_text = update.message.text
        # No specific validation on URL format here, could be added.
        # 'none' is a valid input to skip.
        context.user_data['github_link'] = link_text if link_text.lower() != 'none' else ""
        
        keyboard = [
            [InlineKeyboardButton(status, callback_data=status)]
            for status in STATUS_OPTIONS # STATUS_OPTIONS must be defined
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "What's the current status of your project?",
            reply_markup=reply_markup
        )
        return PROJECT_STATUS
    except Exception as e:
        logger.error(f"Error in github_link: {e}", exc_info=True)
        if update.message: # Ensure message object exists before replying
            await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END


async def project_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    try:
        await query.answer()
        status_choice = query.data
        if status_choice not in STATUS_OPTIONS: # Validate callback data
            await query.edit_message_text("Invalid status selected. Please try creating the project again or contact support.")
            context.user_data.clear()
            return ConversationHandler.END

        context.user_data['status'] = status_choice
        
        await query.edit_message_text( # edit_message_text for callback query
            text=f"Status set to: {status_choice}\n\n"
                 "Finally, what kind of help do you need? (e.g., technical expertise, design, marketing - max 500 characters, type 'none' if not applicable)"
        )
        return HELP_NEEDED
    except Exception as e:
        logger.error(f"Error in project_status: {e}", exc_info=True)
        # query might be None if something went wrong earlier, or message might not be editable
        try:
            await query.edit_message_text("An error occurred processing your status. Please try again.")
        except: # General exception during error reporting
            pass # Logged already
        context.user_data.clear()
        return ConversationHandler.END


async def help_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please describe the help you need or type 'none'.")
            return HELP_NEEDED
        
        help_text = update.message.text
        validate_input(help_text, "Help needed description", MAX_HELP_NEEDED_LENGTH) # Define MAX_HELP_NEEDED_LENGTH
        context.user_data['help_needed'] = help_text if help_text.lower() != 'none' else ""

        if not update.effective_user:
            logger.error("help_needed: update.effective_user is None. Cannot create project without owner.")
            await update.message.reply_text("Error: Could not identify user. Project not created.")
            context.user_data.clear()
            return ConversationHandler.END

        project_data = {
            'Project Name': context.user_data.get('project_name', 'Untitled Project'),
            'Owner Telegram ID': str(update.effective_user.id),
            'One-liner': context.user_data.get('tagline', ''),
            'Problem Statement': context.user_data.get('problem_statement', ''),
            'Stack': context.user_data.get('tech_stack', ''),
            'GitHub/Demo': context.user_data.get('github_link', ''),
            'Status': context.user_data.get('status', 'Idea'), # Default status
            'Help Needed': context.user_data.get('help_needed', ''),
            # 'Timestamp Created': datetime.now(timezone.utc).isoformat() # Optional: Add creation timestamp if Airtable field exists
        }
        
        # Log the data being sent to Airtable, redacting sensitive parts if any in future
        logger.info(f"Attempting to create project in Airtable with data: {project_data}")
        
        new_record = projects_table.create(project_data) # Airtable API call
        logger.info(f"Airtable create response: {new_record}")
            
        await update.message.reply_text(
            "🎉 Your project has been created successfully!\n\n"
            "You can use /myprojects to view your projects."
        )

    except ValidationError as e:
        await update.message.reply_text(str(e))
        return HELP_NEEDED # Stay in current state to allow correction
    except Exception as e: # Catch Airtable errors or other unexpected ones
        logger.error(f"Error saving project to Airtable or during help_needed: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Sorry, there was an error saving your project. Please try the /newproject command again later or contact support if the issue persists."
        )
    
    context.user_data.clear()
    return ConversationHandler.END



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = "Operation cancelled."
    if 'project_name' in context.user_data or 'selected_project_id' in context.user_data : # Check if in a known conversation
        message_text = "Project creation or update cancelled."
    
    if update.message:
        await update.message.reply_text(message_text)
    elif update.callback_query: # If cancel is somehow triggered from a callback
        await update.callback_query.answer("Cancelled")
        try:
            await update.callback_query.edit_message_text(message_text)
        except TelegramError as e: # If message can't be edited (e.g. too old)
             logger.warning(f"Could not edit message on cancel: {e}")
             if update.effective_chat: # Try sending a new message if edit fails
                await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text)

    context.user_data.clear()
    return ConversationHandler.END

# updateproject command is now effectively merged into /myprojects (users select update from there)
# This function can be removed if /updateproject command is removed,
# or kept if direct /updateproject command is desired for some reason.
# For now, let's assume update flow starts via /myprojects and CallbackQueryHandler.
# If you want /updateproject to list projects like /myprojects does for selection:
async def updateproject_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed to avoid conflict
    """This is an alternative entry point if you want /updateproject command directly"""
    if not update.effective_user:
        logger.warning("updateproject_command_entry: update.effective_user is None.")
        if update.message: await update.message.reply_text("Could not identify user.")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    projects = await get_user_projects(user_id)
    
    if not projects:
        if update.message:
            await update.message.reply_text(
                "You don't have any projects yet to update. Use /newproject to create one!"
            )
        return ConversationHandler.END # No projects, end conversation
    
    # Store projects in user_data to be accessed by select_project if needed by this path
    context.user_data['projects_for_update'] = projects 
    
    keyboard = [
        # Using project ID directly in callback_data for selection
        [InlineKeyboardButton(project['fields'].get('Project Name', f"Unnamed Project {project['id']}")[:50], callback_data=f"select_{project['id']}")]
        for project in projects
    ]
    if not keyboard: # Should not happen if projects exist
        if update.message: await update.message.reply_text("No projects found to display for update.")
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(
            "Select a project to update:",
            reply_markup=reply_markup
        )
    return SELECT_PROJECT # State for selecting project via callback



async def select_project_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles project selection from an inline keyboard for the update flow"""
    query = update.callback_query
    if not query or not query.data:
        logger.warning("select_project_for_update: query or query.data is None.")
        return ConversationHandler.END
    await query.answer()

    # Assuming callback_data is like "select_PROJECTID"
    project_id = query.data[len("select_"):] 
    
    # Fetch all projects for the user to ensure ownership and get fresh data
    if not update.effective_user:
        await query.edit_message_text("Error: Could not identify user.")
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    user_projects = await get_user_projects(user_id)

    selected_project = next((p for p in user_projects if p['id'] == project_id), None)
    
    if not selected_project:
        await query.edit_message_text(
            "❌ Error: Project not found or you don't have access. Please try again via /myprojects."
        )
        return ConversationHandler.END
    
    context.user_data['selected_project_id'] = project_id
    context.user_data['selected_project'] = selected_project # Storing the whole dict
    project_name = selected_project.get('fields', {}).get('Project Name', 'the selected project')
    
    await query.edit_message_text(
        f"Updating: *{project_name}*\n\n"
        "What progress have you made this week? (max 1000 characters)",
        parse_mode='Markdown'
    )
    return UPDATE_PROGRESS


async def update_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please provide your progress update.")
            return UPDATE_PROGRESS
        validate_input(update.message.text, "Progress update", MAX_UPDATE_LENGTH) # Define MAX_UPDATE_LENGTH
        context.user_data['progress'] = update.message.text
        
        project_name = context.user_data.get('selected_project', {}).get('fields', {}).get('Project Name', 'your project')
        await update.message.reply_text(
            f"Progress for *{project_name}* noted.\n\n"
            "Are there any blockers or challenges you're facing? (max 500 characters, type 'none' if no blockers)",
            parse_mode='Markdown'
        )
        return UPDATE_BLOCKERS
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return UPDATE_PROGRESS # Stay in current state
    except Exception as e:
        logger.error(f"Error in update_progress: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END



async def update_blockers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            await update.message.reply_text("Please describe blockers or type 'none'.")
            return UPDATE_BLOCKERS

        blockers_text = update.message.text
        validate_input(blockers_text, "Blockers description", MAX_BLOCKERS_LENGTH) # Define MAX_BLOCKERS_LENGTH
        context.user_data['blockers'] = blockers_text if blockers_text.lower() != 'none' else ""

        if not update.effective_user:
            logger.error("update_blockers: update.effective_user is None. Cannot save update.")
            await update.message.reply_text("Error: Could not identify user. Update not saved.")
            context.user_data.clear()
            return ConversationHandler.END
            
        if 'selected_project_id' not in context.user_data:
            logger.error("update_blockers: 'selected_project_id' not in user_data. This should not happen.")
            await update.message.reply_text("Error: No project selected for update. Please start from /myprojects.")
            context.user_data.clear()
            return ConversationHandler.END

        update_data = {
            'Project': [context.user_data['selected_project_id']], # Link to 'Ongoing projects' table
            'Update': context.user_data.get('progress', 'No progress reported.'),
            'Blockers': context.user_data.get('blockers', ''),
            'Updated By Telegram ID': str(update.effective_user.id), # Store who made the update
            # 'Timestamp': datetime.now(timezone.utc).isoformat() # Airtable auto-adds 'Created time'
        }
        
        logger.info(f"Attempting to create update in Airtable with data: {update_data}")
        update_record = updates_table.create(update_data)
        logger.info(f"Airtable create update response: {update_record}")
        
        project_name = context.user_data.get('selected_project', {}).get('fields', {}).get('Project Name', 'Your project')
        await update.message.reply_text(
            f"✅ Update for *{project_name}* has been saved successfully!\n\n"
            "You can view progress via /myprojects or log another update.",
            parse_mode='Markdown'
        )
    except ValidationError as e:
        await update.message.reply_text(str(e))
        return UPDATE_BLOCKERS # Stay in current state
    except Exception as e:
        logger.error(f"Error saving update to Airtable or in update_blockers: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Sorry, there was an error saving your update. Please try again later."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    # Try to inform user if possible
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Apologies, I encountered an unexpected problem. Please try your command again. If the issue persists, the admin has been notified."
            )
        except Exception as e:
            logger.error(f"Error sending message in error_handler: {e}", exc_info=True)
    elif isinstance(update, Update) and update.callback_query:
         try:
            await update.callback_query.answer("Error processing request.", show_alert=True)
            # Optionally send a new message if editing isn't appropriate or fails
            if update.effective_chat:
                 await context.bot.send_message(
                     chat_id=update.effective_chat.id,
                     text="An error occurred with your last action. Please try again."
                 )
         except Exception as e:
            logger.error(f"Error sending message/answering callback in error_handler: {e}", exc_info=True)


def setup_bot_handlers(app_builder: Application) -> None: # Parameter renamed for clarity
    # Error Handler
    app_builder.add_error_handler(error_handler)

    # ConversationHandler for creating a new project
    new_project_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('newproject', newproject)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name)],
            PROJECT_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_tagline)],
            PROBLEM_STATEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, problem_statement)],
            TECH_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tech_stack)],
            GITHUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, github_link)],
            PROJECT_STATUS: [CallbackQueryHandler(project_status)], # Handles status selection from inline keyboard
            HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_needed)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        # per_message=False by default for states, which is usually fine.
        # If you need CallbackQueryHandlers to work even if a new message arrives, consider per_message settings.
        # The PTBUserWarnings you saw are related to this; for now, default is acceptable.
    )

    # ConversationHandler for updating an existing project
    # Entry point is now primarily through /myprojects's inline buttons (handle_project_callback)
    # or optionally via a direct /updateproject command.
    update_project_conv_handler = ConversationHandler(
        entry_points=[
            # This handles "📝 Update <ProjectName>" button from /myprojects
            # It uses handle_project_callback which transitions to UPDATE_PROGRESS
            CallbackQueryHandler(handle_project_callback, pattern=f"^{UPDATE_PREFIX}"),
            # Optional: direct command to list projects for update
            CommandHandler('updateproject', updateproject_command_entry) 
        ],
        states={
            # This state is for when /updateproject command lists projects for selection via callback
            SELECT_PROJECT: [CallbackQueryHandler(select_project_for_update, pattern=f"^select_")], 
            UPDATE_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_progress)],
            UPDATE_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_blockers)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app_builder.add_handler(CommandHandler("start", start))
    app_builder.add_handler(new_project_conv_handler)
    app_builder.add_handler(update_project_conv_handler) 
    app_builder.add_handler(CommandHandler("myprojects", myprojects))
    
    # Handler for "👁 View <ProjectName>" button from /myprojects
    # This is not part of a conversation, it directly displays info or can lead to one if "Update This Project" is pressed.
    app_builder.add_handler(CallbackQueryHandler(handle_project_callback, pattern=f"^{VIEW_PREFIX}"))


async def set_telegram_webhook(bot_token: str, webhook_url: str) -> None:
    set_webhook_url_tg = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    logger.info(f"Attempting to set webhook to: {webhook_url} using httpx.")
    try:
        async with httpx.AsyncClient() as client:
            # Telegram might sometimes return 429 if called too frequently. Consider retry logic if that becomes an issue.
            resp = await client.post(set_webhook_url_tg, data={"url": webhook_url, "allowed_updates": ["message", "callback_query"]})
            resp.raise_for_status() 
            response_data = resp.json()
            if response_data.get("ok"):
                logger.info(f"Successfully set webhook: {response_data.get('description', '')}")
            else:
                logger.error(f"Failed to set webhook, Telegram API error: {response_data.get('description', 'Unknown error')}, Code: {response_data.get('error_code', 'N/A')}")
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to set webhook (HTTP Error): {e.response.status_code} - {e.response.text}",
            exc_info=True
        )
        # Depending on the error, you might want to raise it to stop worker boot
        if e.response.status_code in [401, 404]: # e.g. Bad token, bot deleted
             raise RuntimeError(f"Critical error setting webhook: {e.response.status_code}") from e
    except httpx.RequestError as e: 
        logger.error(f"Failed to set webhook (Request Error, e.g., network issue): {e}", exc_info=True)
        raise RuntimeError("Network error while setting webhook.") from e # Could be transient, but critical for boot
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred while setting webhook: {e}", exc_info=True)
        raise RuntimeError("Unexpected error setting webhook.") from e # Critical for boot


# --- NEW: Function to initialize the bot application per worker ---
async def initialize_telegram_bot_for_worker():
    global application # Ensure we're setting the global var
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    webhook_url = os.getenv('WEBHOOK_URL')

    # Redundant check, already done globally, but good for function atomicity
    if not bot_token or not webhook_url:
        logger.error("TELEGRAM_BOT_TOKEN or WEBHOOK_URL not set; cannot initialize bot application.")
        raise RuntimeError("Missing critical environment variables for Telegram bot.")

    worker_pid = os.getpid() # Get current worker's PID for logging
    logger.info(f"[Worker {worker_pid}] Initializing Telegram Application.")

    try:
        logger.info(f"[Worker {worker_pid}] Building Telegram Application.")
        # Create a temporary instance first
        temp_application = Application.builder().token(bot_token).build()
        logger.info(f"[Worker {worker_pid}] Application object created: {temp_application}")

        logger.info(f"[Worker {worker_pid}] Setting up bot handlers.")
        setup_bot_handlers(temp_application) # Pass the instance to the setup function

        logger.info(f"[Worker {worker_pid}] Initializing Telegram Application internals (awaiting .initialize()).")
        await temp_application.initialize() # CRITICAL STEP: Initialize the application
        logger.info(f"[Worker {worker_pid}] Telegram Application internals initialized successfully.")

        # Assign to global 'application' only after critical initializations are done
        application = temp_application
        logger.info(f"[Worker {worker_pid}] Global 'application' variable has been set.")

        logger.info(f"[Worker {worker_pid}] Attempting to set Telegram webhook to: {webhook_url}")
        await set_telegram_webhook(bot_token, webhook_url)
        # set_telegram_webhook has its own logging for success/failure

        # Call post_init after initialize.
        if hasattr(application, 'post_init') and callable(application.post_init):
            logger.info(f"[Worker {worker_pid}] Calling application.post_init().")
            await application.post_init()
            logger.info(f"[Worker {worker_pid}] application.post_init() completed.")
        else:
            # This addresses the "post_init: None" log. If it's truly None or not callable.
            logger.warning(
                f"[Worker {worker_pid}] application.post_init method not found, not callable, or is None. Skipping. "
                f"Application type: {type(application)}, "
                f"post_init attribute value: {getattr(application, 'post_init', 'Attribute Not Found')}"
            )
        
        logger.info(f"[Worker {worker_pid}] Telegram Application is fully initialized and ready for webhooks.")

    except Exception as e:
        logger.critical(f"[Worker {worker_pid}] Failed during initialize_telegram_bot_for_worker: {e}", exc_info=True)
        application = None # Ensure application is None if initialization failed pathway
        raise # Re-raise the exception to be handled by the caller (e.g., on_worker_boot)
    pass

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
    logger.info(f"Worker {worker.pid} received INT signal (graceful shutdown).")
    if application:
        logger.info(f"Shutting down Telegram Application for worker {worker.pid}.")
        try:
            asyncio.run(application.shutdown())
            logger.info(f"Telegram Application for worker {worker.pid} shut down successfully.")
        except Exception as e:
            logger.error(f"Error during Telegram Application shutdown for worker {worker.pid}: {e}", exc_info=True)


def worker_exit(server, worker):
    """
    Called when a worker is about to exit.
    """
    logger.info(f"Worker {worker.pid} exiting.")
    # No need for shutdown here if worker_int handles it.


def worker_abort(worker):
    logger.warning(f"Worker {worker.pid} aborted (e.g., timeout).")
    if application:
        logger.warning(f"Attempting to shut down Telegram Application due to worker {worker.pid} abort.")
        try:
            asyncio.run(application.shutdown())
            logger.info(f"Telegram Application for worker {worker.pid} (aborted) shut down attempt completed.")
        except Exception as e:
            logger.error(f"Error during Telegram Application shutdown on worker {worker.pid} abort: {e}", exc_info=True)


# --- Gunicorn Worker Setup (Hook into Gunicorn's lifecycle) ---
def on_worker_boot(worker):
    # This log helps confirm the hook is being entered by Gunicorn.
    logger.info(f"APP_HOOK_LOG: on_worker_boot triggered for worker PID {worker.pid}.")
    try:
        asyncio.run(initialize_telegram_bot_for_worker())
        # Check if the global 'application' was actually set by the async function
        if application is None:
            logger.critical(
                f"APP_HOOK_LOG: Worker PID {worker.pid} - initialize_telegram_bot_for_worker completed, "
                "but global 'application' is STILL None. This is a critical failure in worker setup."
            )
            # Raising an exception here will cause Gunicorn to consider this worker boot failed.
            raise RuntimeError(f"Worker PID {worker.pid}: Global 'application' object not set after initialization.")
        else:
            logger.info(
                f"APP_HOOK_LOG: Worker PID {worker.pid} - Global 'application' object successfully set in on_worker_boot."
            )
        logger.info(f"APP_HOOK_LOG: on_worker_boot completed successfully for worker PID {worker.pid}.")
    except Exception as e:
        logger.critical(f"APP_HOOK_LOG: EXCEPTION in on_worker_boot for worker PID {worker.pid}: {e}", exc_info=True)
        # Re-raise the exception so Gunicorn knows the worker failed to boot.
        raise

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
    main()
