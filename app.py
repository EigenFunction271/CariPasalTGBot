# app.py
import os
import logging
from flask import Flask, request as flask_request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv

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
def new_project_start(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    clear_user_data(user_id) # Clear any previous data
    user_data_store[user_id] = {"telegram_id": user_id}
    update.message.reply_text("Let's create a new project! What's the project name?")
    return ASK_PROJECT_NAME

def ask_one_liner(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["project_name"] = update.message.text #
    update.message.reply_text("Great! Now, what's the one-liner tagline for your project?") #
    return ASK_ONE_LINER

def ask_problem(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["one_liner"] = update.message.text #
    update.message.reply_text("What problem is this project trying to solve? (Problem Statement)") #
    return ASK_PROBLEM

def ask_stack(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["problem_statement"] = update.message.text #
    update.message.reply_text("What's the tech stack? (e.g., Python, React, Firebase)") #
    return ASK_STACK

def ask_link(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["stack"] = update.message.text #
    update.message.reply_text("Please provide a GitHub or demo link (URL).") #
    return ASK_LINK

def ask_status(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["github_demo_link"] = update.message.text #
    keyboard = [ #
        [InlineKeyboardButton("Idea", callback_data="status_Idea")],
        [InlineKeyboardButton("MVP", callback_data="status_MVP")],
        [InlineKeyboardButton("Launched", callback_data="status_Launched")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("What's the current stage of the project?", reply_markup=reply_markup)
    return ASK_STATUS

def ask_help_needed(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = get_user_id(update)
    
    # Extract status from callback_data (e.g., "status_Idea" -> "Idea")
    status = query.data.split('_')[1] 
    user_data_store[user_id]["status"] = status #
    
    query.edit_message_text(text=f"Project stage set to: {status}")
    context.bot.send_message(chat_id=user_id, text="What kind of help do you need for this project? (e.g., 'Frontend dev', 'User feedback')") #
    return ASK_HELP_NEEDED

def new_project_save(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["help_needed"] = update.message.text #

    project_payload = {
        "Project Name": user_data_store[user_id].get("project_name"),
        "Owner Telegram ID": user_id,
        "One-liner": user_data_store[user_id].get("one_liner"),
        "Problem Statement": user_data_store[user_id].get("problem_statement"),
        "Stack": user_data_store[user_id].get("stack"),
        "GitHub/Demo": user_data_store[user_id].get("github_demo_link"),
        "Status": user_data_store[user_id].get("status"),
        "Help Needed": user_data_store[user_id].get("help_needed"),
    }

    record = airtable_client.add_project(project_payload)
    if record:
        update.message.reply_text(f"Project '{project_payload['Project Name']}' created successfully!")
    else:
        update.message.reply_text("Sorry, there was an error creating your project. Please try again later.")
    
    clear_user_data(user_id)
    return ConversationHandler.END

# --- /myprojects Command Handler ---
def my_projects(update: Update, context: CallbackContext) -> None:
    user_id = get_user_id(update)
    projects = airtable_client.get_projects_by_user(user_id)

    if not projects:
        update.message.reply_text("You don't have any projects yet. Use /newproject to create one!")
        return

    message = "Here are your projects:\n\n"
    keyboard_buttons = []
    for project in projects:
        fields = project.get('fields', {})
        project_name = fields.get("Project Name", "N/A")
        one_liner = fields.get("One-liner", "") #
        status = fields.get("Status", "N/A") #
        message += f"- *{project_name}* ({status}): {one_liner}\n"
        # Add button to update this specific project
        keyboard_buttons.append(
            [InlineKeyboardButton(f"Update '{project_name}'", callback_data=f"update_{project['id']}")]
        )
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    # The callback_data 'update_{project_id}' will be handled by update_project_start_choose or a specific callback handler

# --- /updateproject Command Handlers ---
def update_project_start_choose(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    clear_user_data(user_id) # Clear any previous state
    user_data_store[user_id] = {"telegram_id": user_id}

    query = update.callback_query 
    # This function can be triggered by /myprojects inline button or directly by /updateproject command
    
    if query: # Called from inline button in /myprojects
        query.answer()
        project_id_to_update = query.data.split('_')[1]
        user_data_store[user_id]["project_to_update_id"] = project_id_to_update
        project_details = airtable_client.get_project_details(project_id_to_update)
        project_name = project_details.get('fields', {}).get('Project Name', 'this project') if project_details else 'this project'
        
        query.edit_message_text(text=f"Updating '{project_name}'. What progress did you make this week?")
        return ASK_PROGRESS_UPDATE
    else: # Called by /updateproject command
        projects = airtable_client.get_projects_by_user(user_id)
        if not projects:
            update.message.reply_text("You don't have any projects to update. Use /newproject to create one first.")
            return ConversationHandler.END

        keyboard = []
        for project in projects:
            project_name = project.get('fields', {}).get("Project Name", "Unnamed Project")
            keyboard.append([InlineKeyboardButton(project_name, callback_data=f"proj_{project['id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Which project do you want to update?", reply_markup=reply_markup)
        return CHOOSE_PROJECT_TO_UPDATE

def handle_project_selection_for_update(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = get_user_id(update)
    
    project_id = query.data.split('_')[1] # e.g., "proj_{id}"
    user_data_store[user_id]["project_to_update_id"] = project_id
    project_details = airtable_client.get_project_details(project_id)
    project_name = project_details.get('fields', {}).get('Project Name', 'this project') if project_details else 'this project'

    query.edit_message_text(text=f"Updating '{project_name}'. What progress did you make this week?") #
    return ASK_PROGRESS_UPDATE

def ask_blockers(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["progress_update"] = update.message.text #
    update.message.reply_text("Any blockers this week? (Type 'None' if no blockers)") #
    return ASK_BLOCKERS

def save_project_update(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    user_data_store[user_id]["blockers"] = update.message.text #

    project_id = user_data_store[user_id].get("project_to_update_id")
    if not project_id:
        update.message.reply_text("Error: Could not find the project to update. Please try starting the update process again.")
        clear_user_data(user_id)
        return ConversationHandler.END

    update_payload = {
        "Project (Linked)": [project_id], # Needs to be a list of record IDs for linked records
        "Update Text": user_data_store[user_id].get("progress_update"),
        "Blockers": user_data_store[user_id].get("blockers"),
        "Updated By": user_id, #
    }

    record = airtable_client.add_update(update_payload)
    if record:
        project_details = airtable_client.get_project_details(project_id)
        project_name = project_details.get('fields', {}).get('Project Name', 'The project') if project_details else 'The project'
        update.message.reply_text(f"Update for '{project_name}' saved successfully!")
    else:
        update.message.reply_text("Sorry, there was an error saving your update. Please try again.")
    
    clear_user_data(user_id)
    return ConversationHandler.END

# --- Fallback and Error Handlers ---
def cancel(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update)
    update.message.reply_text('Operation cancelled.')
    clear_user_data(user_id)
    return ConversationHandler.END

def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        update.effective_message.reply_text('An error occurred. Please try again later.')

# Helper to get target chat_id and message_thread_id for replies in context
def get_reply_params(update: Update) -> dict:
    params = {"chat_id": update.effective_chat.id}
    if update.effective_message and update.effective_message.is_topic_message:
        params["message_thread_id"] = update.effective_message.message_thread_id
    return params

# --- /searchprojects Command Handlers ---
def search_projects_start(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update) # For user_data_store key
    clear_user_data(user_id)
    user_data_store[user_id] = {"search_criteria": {}}
    
    reply_params = get_reply_params(update) # Get chat_id and potential message_thread_id

    keyboard = [[InlineKeyboardButton("Skip Keyword", callback_data="search_skip_keyword")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # If the initial command is from a topic, this reply_text will go to the topic.
    # If it's a DM, it goes to the DM.
    update.message.reply_text( 
        "Let's find some projects! Enter a keyword to search in name, tagline, or problem statement (or skip):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_KEYWORD

def handle_search_keyword(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update) # For user_data_store key
    query = update.callback_query
    
    # Determine where to send the next prompt based on original interaction
    # If original update was a message, use that context. If it's a query, use query's message context.
    effective_update_for_context = query if query else update
    reply_params = get_reply_params(effective_update_for_context)


    if query: # Skipped keyword
        query.answer()
        # Edit the message that had the "Skip Keyword" button
        query.edit_message_text("Keyword skipped.")
    else: # Keyword provided by text message
        user_data_store[user_id]["search_criteria"]["keyword"] = update.message.text
        # Reply to the message that provided the keyword
        update.message.reply_text("Got it. Keyword set.")


    keyboard = [[InlineKeyboardButton("Skip Stack", callback_data="search_skip_stack")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(
        **reply_params, # Unpack chat_id and message_thread_id
        text="Enter a tech stack to filter by (e.g., Python, React) (or skip):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_STACK


def handle_search_stack(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update) # For user_data_store key
    query = update.callback_query
    
    effective_update_for_context = query if query else update
    reply_params = get_reply_params(effective_update_for_context)

    if query: # Skipped stack via callback
        query.answer()
        query.edit_message_text("Stack filter skipped.")
    else: # Stack provided via text message
        user_data_store[user_id]["search_criteria"]["stack"] = update.message.text
        update.message.reply_text("Tech stack filter set.")

    status_keyboard = [
        [InlineKeyboardButton("Idea", callback_data="search_status_Idea")],
        [InlineKeyboardButton("MVP", callback_data="search_status_MVP")],
        [InlineKeyboardButton("Launched", callback_data="search_status_Launched")],
        [InlineKeyboardButton("Any Status", callback_data="search_skip_status")]
    ]
    reply_markup = InlineKeyboardMarkup(status_keyboard)
    context.bot.send_message(
        **reply_params, # Unpack chat_id and message_thread_id
        text="Filter by project status (or choose any):",
        reply_markup=reply_markup
    )
    return ASK_SEARCH_STATUS

def process_and_display_search_results(update: Update, context: CallbackContext) -> int:
    user_id = get_user_id(update) # For user_data_store key
    query = update.callback_query # This handler is only triggered by callback
    
    # The query is from a message previously sent by the bot (e.g. the status selection message)
    # We want the final results to go to the same chat/topic as that message.
    reply_params = {"chat_id": query.message.chat_id}
    if query.message.is_topic_message:
        reply_params["message_thread_id"] = query.message.message_thread_id
        
    query.answer()

    if not query.data == "search_skip_status":
        status = query.data.split('_')[2]
        user_data_store[user_id]["search_criteria"]["status"] = status
        query.edit_message_text(f"Status filter set to: {status}") # Edits the status selection message
    else:
        query.edit_message_text("Status filter skipped (any status).")

    criteria = user_data_store[user_id].get("search_criteria", {})
    
    if not any(criteria.values()): # Check if all values in criteria are None or empty
        context.bot.send_message(
            **reply_params,
            text="No search criteria provided. Please try again with at least one filter."
        )
        clear_user_data(user_id)
        return ConversationHandler.END

    # Send a "Searching..." message to the same context
    context.bot.send_message(**reply_params, text=f"Searching with criteria: {criteria}...")
    
    results = airtable_client.search_projects(criteria)

    if not results:
        context.bot.send_message(**reply_params, text="No projects found matching your criteria.")
    else:
        message_parts = ["*Search Results:*\n\n"]
        for project in results[:10]: # Limit results
            fields = project.get('fields', {})
            # ... (formatting logic for each project) ...
            project_name = fields.get("Project Name", "N/A")
            one_liner = fields.get("One-liner", "") #
            status = fields.get("Status", "N/A") #
            stack = fields.get("Stack", "N/A") #
            message_parts.append(f"- *{project_name}* ({status})\n")
            message_parts.append(f"  _Stack:_ {stack}\n")
            message_parts.append(f"  _Tagline:_ {one_liner}\n\n")
        
        if len(results) > 10:
            message_parts.append(f"\n...and {len(results) - 10} more. Consider refining your search.")
        
        final_message = "".join(message_parts)
        context.bot.send_message(**reply_params, text=final_message, parse_mode='Markdown')

    clear_user_data(user_id)
    return ConversationHandler.END

# Apply similar `get_reply_params` logic or direct `message_thread_id` handling
# to other handlers like /newproject and /updateproject if you want their
# non-reply/non-edit messages to also stay within topics when invoked there.



# --- Flask App Setup ---
flask_app = Flask(__name__)
telegram_app = None  # Initialize as None, will be set in main()

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if telegram_app is None:
        return 'Bot not initialized', 500
    # Process the update from Telegram
    # This will be called by the `Application` instance from `python-telegram-bot`
    # when it's configured to use webhooks.
    # The actual processing is handled by the `telegram_app` dispatcher.
    json_data = flask_request.get_json(force=True)
    update = Update.de_json(json_data, telegram_app.bot)
    telegram_app.update_queue.put(update)
    return 'ok', 200

@flask_app.route('/ping', methods=['GET'])
def ping():
    return 'pong', 200

def main() -> None:
    """Start the bot."""
    global telegram_app # Make it global so webhook can access it

    # Create the Application and pass it your bot's token.
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- ConversationHandler for /newproject ---
    new_project_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('newproject', new_project_start)],
        states={
            ASK_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_one_liner)],
            ASK_ONE_LINER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_problem)],
            ASK_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_stack)],
            ASK_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_link)],
            ASK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_status)], # Ideally validate URL here
            ASK_STATUS: [CallbackQueryHandler(ask_help_needed, pattern='^status_')],
            ASK_HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_project_save)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # --- ConversationHandler for /updateproject ---
    update_project_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('updateproject', update_project_start_choose), #
            CallbackQueryHandler(update_project_start_choose, pattern='^update_') # From /myprojects
        ],
        states={
            CHOOSE_PROJECT_TO_UPDATE: [CallbackQueryHandler(handle_project_selection_for_update, pattern='^proj_')],
            ASK_PROGRESS_UPDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_blockers)],
            ASK_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_project_update)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # --- ConversationHandler for /searchprojects ---
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
    
    # Add all handlers
    telegram_app.add_handler(new_project_conv_handler)
    telegram_app.add_handler(update_project_conv_handler)
    telegram_app.add_handler(search_conv_handler)
    telegram_app.add_handler(CommandHandler('myprojects', my_projects))
    
    # Error handler
    telegram_app.add_error_handler(error_handler)

    # Set up webhook if WEBHOOK_URL is defined (for Render deployment)

    
    if WEBHOOK_URL:
        logger.info(f"Setting webhook to {WEBHOOK_URL}/webhook")
        # The line below is where the full URL including the path is constructed
        success = telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        if success:
            logger.info("Webhook set successfully!")
        else:
            logger.error("Failed to set webhook.")
  
  
# Entry point for Gunicorn or other WSGI servers
application = flask_app

if __name__ == '__main__':
    main()  # Set up handlers and webhook if URL is present
    
    if not WEBHOOK_URL:
        logger.info("Running Telegram bot with polling locally...")
        telegram_app.run_polling()
    else:
        logger.info("Flask app ready to receive webhooks. Make sure Gunicorn or similar is serving this app in production.")
        # For local testing of webhook setup
        flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))