# app.py
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv
import asyncio
import threading
from datetime import datetime

import airtable_client # Our Airtable interaction module

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL') # Your Render app's URL for the webhook

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN missing in environment variables.")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation States for /newproject ---
(ASK_PROJECT_NAME, ASK_ONE_LINER, ASK_PROBLEM, ASK_STACK, 
 ASK_LINK, ASK_STATUS, ASK_HELP_NEEDED) = range(7)

# --- Conversation States for /updateproject ---
(CHOOSE_PROJECT_TO_UPDATE, ASK_PROGRESS_UPDATE, ASK_BLOCKERS) = range(7, 10)


# --- Conversation States for /searchprojects ---
(ASK_SEARCH_KEYWORD, ASK_SEARCH_STACK, ASK_SEARCH_STATUS, PROCESS_SEARCH) = range(10, 14) # Ensure unique range


# In-memory store for conversation data (NOT SUITABLE FOR PRODUCTION at scale)
user_data_store = {} 

# --- Helper Functions ---
def get_user_id(update: Update) -> str:
    return str(update.effective_user.id)

def clear_user_data(user_id: str):
    if user_id in user_data_store:
        del user_data_store[user_id]

# --- /newproject Command Handlers ---
async def new_project_start(update: Update, context: CallbackContext) -> int:
    logger.info(f"HANDLER TRIGGERED: new_project_start by user {update.effective_user.id}")
    user_id = get_user_id(update)
    clear_user_data(user_id)
    user_data_store[user_id] = {"telegram_id": user_id}
    await update.message.reply_text("Let's create a new project! What's the project name?")
    return ASK_PROJECT_NAME

async def ask_one_liner(update: Update, context: CallbackContext) -> int:
    """Handle the project name and ask for one-liner."""
    try:
        user_id = get_user_id(update)
        project_name = update.message.text
        logger.info(f"Received project name '{project_name}' from user {user_id}")
        
        user_data_store[user_id] = {"project_name": project_name}
        logger.info(f"Stored project name in user_data_store for user {user_id}")
        
        await update.message.reply_text("Great! Now, what's the one-liner tagline for your project?")
        logger.info(f"Sent one-liner request to user {user_id}")
        return ASK_ONE_LINER
    except Exception as e:
        logger.error(f"Error in ask_one_liner: {e}", exc_info=True)
        if update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, there was an error processing your project name. Please try /newproject again."
            )
        return ConversationHandler.END

async def ask_problem(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["one_liner"] = update.message.text
    await update.message.reply_text("What problem is this project trying to solve? (Problem Statement)")
    return ASK_PROBLEM

async def ask_stack(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["problem_statement"] = update.message.text
    await update.message.reply_text("What's the tech stack? (e.g., Python, React, Firebase)")
    return ASK_STACK

async def ask_link(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["stack"] = update.message.text
    await update.message.reply_text(
        "Please provide a GitHub or demo link (URL) if you have one.\n"
        "You can also type 'skip' to continue without a link."
    )
    return ASK_LINK

async def ask_status(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["github_demo_link"] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Idea", callback_data="status_Idea")],
        [InlineKeyboardButton("MVP", callback_data="status_MVP")],
        [InlineKeyboardButton("Launched", callback_data="status_Launched")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "What's the current stage of the project?\n\n"
        "• Idea: Early concept, no code required\n"
        "• MVP: Working prototype, requires GitHub/demo link\n"
        "• Launched: Live product, requires GitHub/demo link",
        reply_markup=reply_markup
    )
    return ASK_STATUS

async def ask_help_needed(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = get_user_id(update)
    status = query.data.split('_')[1]
    user_data_store[user_id]["status"] = status
    await query.edit_message_text(text=f"Project stage set to: {status}")
    await context.bot.send_message(chat_id=user_id, text="What kind of help do you need for this project? (e.g., 'Frontend dev', 'User feedback')")
    return ASK_HELP_NEEDED

async def new_project_save(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["help_needed"] = update.message.text

    project_payload = {
        "Project Name": user_data_store[user_id].get("project_name"),
        "Owner Telegram ID": user_id,
        "One-liner": user_data_store[user_id].get("one_liner"),
        "Problem Statement": user_data_store[user_id].get("problem_statement"),
        "Stack": user_data_store[user_id].get("stack"),
        "Status": user_data_store[user_id].get("status"),
        "Help Needed": user_data_store[user_id].get("help_needed"),
    }

    # Only include GitHub/Demo if it's not empty and not 'skip'
    github_demo = user_data_store[user_id].get("github_demo_link", "").strip().lower()
    if github_demo and github_demo != 'skip':
        project_payload["GitHub/Demo"] = github_demo

    record = airtable_client.add_project(project_payload)
    if record:
        await update.message.reply_text(f"Project '{project_payload['Project Name']}' created successfully!")
    else:
        await update.message.reply_text(
            "Sorry, there was an error creating your project. Please try again later."
        )
    
    clear_user_data(user_id)
    return ConversationHandler.END

# --- /myprojects Command Handler ---
async def my_projects(update: Update, context: CallbackContext) -> None:
    user_id = get_user_id(update)
    projects = airtable_client.get_projects_by_user(user_id)

    if not projects:
        await update.message.reply_text("You don't have any projects yet. Use /newproject to create one!")
        return

    message = "Here are your projects:\n\n"
    keyboard_buttons = []
    for project in projects:
        fields = project.get('fields', {})
        project_name = fields.get("Project Name", "N/A")
        one_liner = fields.get("One-liner", "")
        status = fields.get("Status", "N/A")
        message += f"- *{project_name}* ({status}): {one_liner}\n"
        keyboard_buttons.append(
            [InlineKeyboardButton(f"Update '{project_name}'", callback_data=f"update_{project['id']}")]
        )
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

# --- /updateproject Command Handlers ---
async def update_project_start_choose(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    clear_user_data(user_id)
    user_data_store[user_id] = {"telegram_id": user_id}

    query = update.callback_query
    if query:
        await query.answer()
        project_id_to_update = query.data.split('_')[1]
        user_data_store[user_id]["project_to_update_id"] = project_id_to_update
        project_details = airtable_client.get_project_details(project_id_to_update)
        project_name = project_details.get('fields', {}).get('Project Name', 'this project') if project_details else 'this project'
        
        await query.edit_message_text(text=f"Updating '{project_name}'. What progress did you make this week?")
        return ASK_PROGRESS_UPDATE
    else:
        projects = airtable_client.get_projects_by_user(user_id)
        if not projects:
            await update.message.reply_text("You don't have any projects to update. Use /newproject to create one first.")
            return ConversationHandler.END

        keyboard = []
        for project in projects:
            project_name = project.get('fields', {}).get("Project Name", "Unnamed Project")
            keyboard.append([InlineKeyboardButton(project_name, callback_data=f"proj_{project['id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Which project do you want to update?", reply_markup=reply_markup)
        return CHOOSE_PROJECT_TO_UPDATE

async def handle_project_selection_for_update(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = get_user_id(update)
    
    project_id = query.data.split('_')[1]
    user_data_store[user_id]["project_to_update_id"] = project_id
    project_details = airtable_client.get_project_details(project_id)
    project_name = project_details.get('fields', {}).get('Project Name', 'this project') if project_details else 'this project'

    await query.edit_message_text(text=f"Updating '{project_name}'. What progress did you make this week?")
    return ASK_PROGRESS_UPDATE

async def ask_blockers(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["progress_update"] = update.message.text
    await update.message.reply_text("Any blockers this week? (Type 'None' if no blockers)")
    return ASK_BLOCKERS

async def save_project_update(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["blockers"] = update.message.text

    project_id = user_data_store[user_id].get("project_to_update_id")
    if not project_id:
        await update.message.reply_text("Error: Could not find the project to update. Please try starting the update process again.")
        clear_user_data(user_id)
        return ConversationHandler.END

    update_payload = {
        "Project": [project_id],
        "Update Text": user_data_store[user_id].get("progress_update"),
        "Blockers": user_data_store[user_id].get("blockers"),
        "Updated By": user_id,
    }

    record = airtable_client.add_update(update_payload)
    if record:
        project_details = airtable_client.get_project_details(project_id)
        project_name = project_details.get('fields', {}).get('Project Name', 'The project') if project_details else 'The project'
        await update.message.reply_text(f"Update for '{project_name}' saved successfully!")
    else:
        await update.message.reply_text("Sorry, there was an error saving your update. Please try again.")
    
    clear_user_data(user_id)
    return ConversationHandler.END

# --- /searchprojects Command Handlers ---
async def search_projects_start(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    clear_user_data(user_id)
    user_data_store[user_id] = {"search_criteria": {}}
    
    reply_params = get_reply_params(update)

    keyboard = [[InlineKeyboardButton("Skip Keyword", callback_data="search_skip_keyword")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Let's find some projects! Enter a keyword to search in name, tagline, or problem statement (or skip):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_KEYWORD

async def handle_search_keyword(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    query = update.callback_query
    
    effective_update_for_context = query if query else update
    reply_params = get_reply_params(effective_update_for_context)

    if query:
        await query.answer()
        await query.edit_message_text("Keyword skipped.")
    else:
        user_data_store[user_id]["search_criteria"]["keyword"] = update.message.text
        await update.message.reply_text("Got it. Keyword set.")

    keyboard = [[InlineKeyboardButton("Skip Stack", callback_data="search_skip_stack")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        **reply_params,
        text="Enter a tech stack to filter by (e.g., Python, React) (or skip):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_STACK

async def handle_search_stack(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    query = update.callback_query
    
    effective_update_for_context = query if query else update
    reply_params = get_reply_params(effective_update_for_context)

    if query:
        await query.answer()
        await query.edit_message_text("Stack filter skipped.")
    else:
        user_data_store[user_id]["search_criteria"]["stack"] = update.message.text
        await update.message.reply_text("Tech stack filter set.")

    status_keyboard = [
        [InlineKeyboardButton("Idea", callback_data="search_status_Idea")],
        [InlineKeyboardButton("MVP", callback_data="search_status_MVP")],
        [InlineKeyboardButton("Launched", callback_data="search_status_Launched")],
        [InlineKeyboardButton("Any Status", callback_data="search_skip_status")]
    ]
    reply_markup = InlineKeyboardMarkup(status_keyboard)
    await context.bot.send_message(
        **reply_params,
        text="Filter by project status (or choose any):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_STATUS

async def process_and_display_search_results(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    query = update.callback_query
    
    reply_params = {"chat_id": query.message.chat_id}
    if query.message.is_topic_message:
        reply_params["message_thread_id"] = query.message.message_thread_id
        
    await query.answer()

    if not query.data == "search_skip_status":
        status = query.data.split('_')[2]
        user_data_store[user_id]["search_criteria"]["status"] = status
        await query.edit_message_text(f"Status filter set to: {status}")
    else:
        await query.edit_message_text("Status filter skipped (any status).")

    criteria = user_data_store[user_id].get("search_criteria", {})
    
    if not any(criteria.values()):
        await context.bot.send_message(
            **reply_params,
            text="No search criteria provided. Please try again with at least one filter."
        )
        clear_user_data(user_id)
        return ConversationHandler.END

    await context.bot.send_message(**reply_params, text=f"Searching with criteria: {criteria}...")
    
    results = airtable_client.search_projects(criteria)

    if not results:
        await context.bot.send_message(**reply_params, text="No projects found matching your criteria.")
    else:
        message_parts = ["*Search Results:*\n\n"]
        for project in results[:10]:
            fields = project.get('fields', {})
            project_name = fields.get("Project Name", "N/A")
            one_liner = fields.get("One-liner", "")
            status = fields.get("Status", "N/A")
            stack = fields.get("Stack", "N/A")
            message_parts.append(f"- *{project_name}* ({status})\n")
            message_parts.append(f"  _Stack:_ {stack}\n")
            message_parts.append(f"  _Tagline:_ {one_liner}\n\n")
        
        if len(results) > 10:
            message_parts.append(f"\n...and {len(results) - 10} more. Consider refining your search.")
        
        final_message = "".join(message_parts)
        await context.bot.send_message(**reply_params, text=final_message, parse_mode='Markdown')

    clear_user_data(user_id)
    return ConversationHandler.END

# --- Fallback and Error Handlers ---
async def cancel(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    if update.message:
        await update.message.reply_text('Operation cancelled.')
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text('Operation cancelled.')
    clear_user_data(user_id)
    return ConversationHandler.END

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text('An error occurred. Please try again later.')
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

# Helper to get target chat_id and message_thread_id for replies in context
def get_reply_params(update: Update) -> dict:
    params = {"chat_id": update.effective_chat.id}
    if update.effective_message and update.effective_message.is_topic_message:
        params["message_thread_id"] = update.effective_message.message_thread_id
    return params

# --- Command Handlers in setup_all_handlers ---
async def start_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) started the bot")
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm the Project Tracker bot. "
        "Use /newproject to create a new project, or /help to see all commands."
    )

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) requested help")
    help_text = (
        "*Available Commands:*\n\n"
        "/newproject - Create a new project\n"
        "/updateproject - Update an existing project\n"
        "/myprojects - View your projects\n"
        "/searchprojects - Search for projects\n"
        "/help - Show this help message\n"
        "/cancel - Cancel current operation"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# --- FastAPI App Setup ---
app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

def setup_all_handlers(app_instance: Application):
    logger.info("Setting up all handlers...")
    try:
        # Add a start command handler
        async def start_command(update: Update, context: CallbackContext) -> None:
            """Send a message when the command /start is issued."""
            user = update.effective_user
            logger.info(f"User {user.id} ({user.first_name}) started the bot")
            await update.message.reply_text(
                f"Hi {user.first_name}! I'm the Project Tracker bot. "
                "Use /newproject to create a new project, or /help to see all commands."
            )

        # Add help command handler
        async def help_command(update: Update, context: CallbackContext) -> None:
            """Send a message when the command /help is issued."""
            user = update.effective_user
            logger.info(f"User {user.id} ({user.first_name}) requested help")
            help_text = (
                "*Available Commands:*\n\n"
                "/newproject - Create a new project\n"
                "/updateproject - Update an existing project\n"
                "/myprojects - View your projects\n"
                "/searchprojects - Search for projects\n"
                "/help - Show this help message\n"
                "/cancel - Cancel current operation"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')

        # ConversationHandler for /newproject
        new_project_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('newproject', new_project_start)],
            states={
                ASK_PROJECT_NAME: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        ask_one_liner,
                        block=False
                    )
                ],
                ASK_ONE_LINER: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        ask_problem,
                        block=False
                    )
                ],
                ASK_PROBLEM: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        ask_stack,
                        block=False
                    )
                ],
                ASK_STACK: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        ask_link,
                        block=False
                    )
                ],
                ASK_LINK: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        ask_status,
                        block=False
                    )
                ],
                ASK_STATUS: [
                    CallbackQueryHandler(
                        ask_help_needed,
                        pattern='^status_'
                    )
                ],
                ASK_HELP_NEEDED: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        new_project_save,
                        block=False
                    )
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            name="new_project",
            persistent=False,
            allow_reentry=True
        )

        # ConversationHandler for /updateproject
        update_project_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('updateproject', update_project_start_choose),
                CallbackQueryHandler(update_project_start_choose, pattern='^update_')
            ],
            states={
                CHOOSE_PROJECT_TO_UPDATE: [CallbackQueryHandler(handle_project_selection_for_update, pattern='^proj_')],
                ASK_PROGRESS_UPDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_blockers)],
                ASK_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_project_update)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        # ConversationHandler for /searchprojects
        search_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('searchprojects', search_projects_start)],
            states={
                ASK_SEARCH_KEYWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_keyword),
                    CallbackQueryHandler(handle_search_keyword, pattern='^search_skip_keyword$')
                ],
                ASK_SEARCH_STACK: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_stack),
                    CallbackQueryHandler(handle_search_stack, pattern='^search_skip_stack$')
                ],
                ASK_SEARCH_STATUS: [
                    CallbackQueryHandler(process_and_display_search_results, pattern='^search_status_|^search_skip_status$')
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        app_instance.add_handler(CommandHandler('start', start_command))
        app_instance.add_handler(CommandHandler('help', help_command))
        app_instance.add_handler(new_project_conv_handler)
        app_instance.add_handler(update_project_conv_handler)
        app_instance.add_handler(search_conv_handler)
        app_instance.add_handler(CommandHandler('myprojects', my_projects))
        app_instance.add_error_handler(error_handler)
        logger.info("All handlers set up successfully")
        handler_names = []
        for handler_list in app_instance.handlers.values():
            # handler_list can be a list or a single handler
            if isinstance(handler_list, list):
                for h in handler_list:
                    if hasattr(h, 'callback'):
                        handler_names.append(h.callback.__name__)
                    else:
                        handler_names.append(str(h))
            else:
                h = handler_list
                if hasattr(h, 'callback'):
                    handler_names.append(h.callback.__name__)
                else:
                    handler_names.append(str(h))
        logger.info(f"Registered handlers: {handler_names}")
    except Exception as e:
        logger.error(f"Error setting up handlers: {e}", exc_info=True)
        raise

# Call setup_handlers for the global telegram_app instance AT MODULE LEVEL
setup_all_handlers(telegram_app)

# --- PTB Threading Setup ---
# IMPORTANT: For production, use Gunicorn with --preload to ensure only one PTB thread is started.
# Example: gunicorn --preload --workers 1 app:application
# If you use multiple workers without --preload, each worker will start its own PTB thread, which can cause issues.

# In ptb_thread_target function:
def ptb_thread_target(app: Application, webhook_url_base: str):
    logger.info("PTB thread target started.")
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop) # Set this loop as the current loop for this thread

    async def actual_ptb_operations():
        """Encapsulates all async operations for the PTB application within this thread."""
        logger.info("PTB Thread (async task): Initializing application...")
        await app.initialize() # initialize() is a coroutine
        logger.info("PTB Thread (async task): Application initialized.")

        if webhook_url_base:
            webhook_full_url = f"{webhook_url_base}/webhook"
            logger.info(f"PTB Thread (async task): Setting webhook to {webhook_full_url}")
            await app.bot.set_webhook(url=webhook_full_url, allowed_updates=Update.ALL_TYPES) # set_webhook() is a coroutine
            logger.info("PTB Thread (async task): Webhook set successfully.")
        else:
            logger.warning("PTB Thread (async task): WEBHOOK_URL not provided, skipping webhook setup.")
        
        logger.info("PTB Thread (async task): Calling await app.start() to start PTB components...")
        await app.start() # This starts the Dispatcher and other components.
                          # It prepares them to run within the active event loop.
        logger.info("PTB Thread (async task): PTB components started via app.start(). Dispatcher is now active.")

        # Keep this coroutine alive so the event loop (run by run_until_complete in the outer function)
        # keeps running. The Dispatcher will use this running loop to process items from app.update_queue.
        logger.info("PTB Thread (async task): Entering main keep-alive loop for dispatcher...")
        try:
            while True: 
                await asyncio.sleep(1) # Sleep for 1 second. This keeps the loop spinning
                                       # and allows other tasks (like the Dispatcher) to run.
                                       # Adjust sleep time if needed, but 1s is often fine.
        except asyncio.CancelledError:
            # This will be raised if the task running actual_ptb_operations is cancelled,
            # for example, during a graceful shutdown.
            logger.info("PTB Thread (async task): Main keep-alive loop was cancelled.")
            raise # Re-raise to allow outer try/except to handle cleanup.
        finally:
            logger.info("PTB Thread (async task): Exiting main keep-alive loop.")


    try:
        # Run the main async logic for the PTB application.
        # loop.run_until_complete will block this thread until actual_ptb_operations() finishes.
        # actual_ptb_operations() will now only finish if its keep-alive loop is broken (e.g., by an exception like CancelledError).
        loop.run_until_complete(actual_ptb_operations())
    
    except KeyboardInterrupt:
        logger.info("PTB Thread: KeyboardInterrupt received by run_until_complete.")
        # Optionally, if you want to signal the async part to stop:
        # (This requires more complex signal handling to set an event that the while loop checks)
    except asyncio.CancelledError:
        logger.info("PTB Thread: actual_ptb_operations task was cancelled externally.")
    except Exception as e:
        logger.error(f"PTB thread's run_until_complete encountered an unhandled exception: {e}", exc_info=True)
    finally:
        logger.info("PTB Thread: Reached finally block of ptb_thread_target. Ensuring application is stopped.")
        
        if app.running: 
            logger.info("PTB Thread: Application is marked as running, attempting to stop components gracefully...")
            if not loop.is_closed():
                # Ensure stop is only called if the loop isn't already trying to shut down tasks from a CancelledError
                try:
                    loop.run_until_complete(app.stop()) # app.stop() is also a coroutine
                    logger.info("PTB Thread: app.stop() completed.")
                except Exception as e_stop:
                    logger.error(f"PTB Thread: Exception during app.stop(): {e_stop}", exc_info=True)
            else:
                logger.warning("PTB Thread: Loop was already closed when trying to run app.stop().")
        
        if not loop.is_closed():
            # Attempt to gracefully close the loop and cancel any remaining tasks
            try:
                logger.info("PTB Thread: Performing final cleanup of event loop tasks...")
                # Get all tasks for the loop
                tasks = asyncio.all_tasks(loop)
                if tasks:
                    for task in tasks:
                        if not task.done() and not task.cancelled():
                            task.cancel()
                    # Wait for tasks to cancel
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    logger.info("PTB Thread: Remaining tasks cancelled.")
                else:
                    logger.info("PTB Thread: No remaining tasks to cancel.")
                
                # Run the loop until all tasks are surely done
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception as e_shutdown:
                logger.error(f"PTB Thread: Error during loop shutdown tasks: {e_shutdown}", exc_info=True)
            finally: # Ensure loop close is attempted
                loop.close()
                logger.info("PTB Thread: Event loop closed.")
        logger.info("PTB Thread: Thread target function finishing.")

        
# Start the PTB thread only once.
# The check for WERKZEUG_RUN_MAIN is for Flask's dev server reloader.
# For Gunicorn, if you use --preload, this module-level code runs once in the master process.
# If not using --preload, each worker will try to start a thread. This is usually fine as
# they operate on the same `telegram_app` object, but `--preload` is cleaner for shared setup.
if not os.environ.get("WERKZEUG_RUN_MAIN") or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    if int(os.environ.get("WEB_CONCURRENCY", "1")) > 1 and not os.environ.get("PRELOAD", "0") == "1":
        logger.warning("Multiple Gunicorn workers detected without --preload. This may start multiple PTB threads. Use --preload for a single PTB thread.")
    logger.info("Attempting to start PTB background thread...")
    ptb_background_thread = threading.Thread(target=ptb_thread_target, args=(telegram_app, WEBHOOK_URL), daemon=True)
    ptb_background_thread.start()
    logger.info(f"PTB background thread initiated: {ptb_background_thread.name}")
else:
    logger.info("Skipping PTB background thread start (likely Werkzeug reloader child process or similar).")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_data = await request.json()
        update_id = json_data.get('update_id', 'unknown')
        logger.info(f"Received webhook update {update_id}")
        
        update = Update.de_json(json_data, telegram_app.bot)
        
        if hasattr(telegram_app, 'update_queue') and telegram_app.update_queue:
            logger.info(f"Processing update {update_id}...")
            await telegram_app.update_queue.put(update)
            logger.info(f"Update {update_id} successfully queued")
            return {"status": "ok", "update_id": update_id}
        else:
            logger.error("CRITICAL: telegram_app.update_queue is None! PTB app might not have started correctly.")
            raise HTTPException(status_code=500, detail="Update queue not available")
            
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
@app.head("/")  # Add HEAD method support
async def root():
    """Root endpoint for health checks and basic info."""
    return {
        "status": "ok",
        "service": "Loophole Project Tracker Bot",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook",
            "health": "/ping"
        }
    }

@app.get("/ping")
@app.head("/ping")  # Add HEAD method support
async def ping():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# Add graceful shutdown handling
@app.on_event("shutdown")
async def shutdown_event():
    """Handle graceful shutdown of the application."""
    logger.info("Shutting down application...")
    if telegram_app.running:
        logger.info("Stopping PTB application...")
        await telegram_app.stop()
        logger.info("PTB application stopped.")
    logger.info("Application shutdown complete.")

# Entry point for Gunicorn or other ASGI servers
application = app

if __name__ == '__main__':
    import uvicorn
    if WEBHOOK_URL:
        logger.info("Running FastAPI app locally for webhook testing (PTB thread should be active).")
        uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
    else:
        # For local polling, we don't need the FastAPI app or the PTB webhook thread.
        # We'll run a separate polling instance.
        logger.info("WEBHOOK_URL not set. Running Telegram bot with polling locally (new instance)...")
        
        # Create a new application instance specifically for polling to avoid conflicts with the threaded one.
        polling_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        setup_all_handlers(polling_app) # Setup handlers for this new instance
        
        logger.info("Starting polling...")
        polling_app.run_polling(allowed_updates=Update.ALL_TYPES)

def log_handler_errors(func):
    async def wrapper(update: Update, context: CallbackContext):
        try:
            return await func(update, context)
        except Exception as e:
            logger.error(f"Error in handler {func.__name__}: {e}", exc_info=True)
            if update and update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        'An error occurred. Please try again later.'
                    )
                except Exception as reply_error:
                    logger.error(f"Failed to send error message: {reply_error}")
            return ConversationHandler.END
    return wrapper
