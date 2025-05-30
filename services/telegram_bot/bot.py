import os
import asyncio
import logging
from typing import Optional
from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

# Import handlers
from handlers.new_project import (
    newproject_entry_point, project_name_state, project_tagline_state,
    problem_statement_state, tech_stack_state, github_link_state,
    project_status_state_callback, help_needed_state, cancel_conversation
)
from handlers.update_project import (
    handle_project_action_callback as update_project_action_callback,
    update_progress_state, update_blockers_state,
    select_project_for_update
)
from handlers.myprojects import my_projects_command
from handlers.view_project import handle_project_action_callback as view_project_action_callback

# Import constants and database from utils
from utils.constants import (
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK,
    GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED, SELECT_PROJECT,
    UPDATE_PROGRESS, UPDATE_BLOCKERS, STATUS_OPTIONS,
    UPDATE_PROJECT_PREFIX, VIEW_PROJECT_PREFIX, SELECT_PROJECT_PREFIX,
    logger
)

# --- Environment Setup ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
USE_LONG_POLLING = os.getenv('USE_LONG_POLLING', 'true').lower() == 'true'

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

# --- Bot Setup Functions ---
async def set_commands(application: Application) -> None:
    """Set bot commands in Telegram."""
    commands = [
        BotCommand("start", "🚀 Welcome & instructions"),
        BotCommand("newproject", "✨ Create a new project"),
        BotCommand("myprojects", "📂 View & manage your projects"),
        BotCommand("cancel", "❌ Cancel current operation"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands successfully set in Telegram.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}", exc_info=True)

async def error_handler(update: object, context: object) -> None:
    """Global error handler for the bot."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    if hasattr(update, 'effective_message'):
        try:
            await update.effective_message.reply_text(
                "🤖 Apologies, an unexpected error occurred. Please try again."
            )
        except Exception as e:
            logger.error(f"Error sending error reply: {e}", exc_info=True)

def setup_handlers(application: Application) -> None:
    """Set up all bot handlers."""
    # Add error handler
    application.add_error_handler(error_handler)

    # New Project Conversation
    new_project_conv = ConversationHandler(
        entry_points=[CommandHandler('newproject', newproject_entry_point)],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name_state)],
            PROJECT_TAGLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_tagline_state)],
            PROBLEM_STATEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, problem_statement_state)],
            TECH_STACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tech_stack_state)],
            GITHUB_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, github_link_state)],
            PROJECT_STATUS: [CallbackQueryHandler(project_status_state_callback, pattern=f"^({'|'.join(STATUS_OPTIONS)})$")],
            HELP_NEEDED: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_needed_state)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    application.add_handler(new_project_conv)

    # Update Project Conversation
    update_project_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(update_project_action_callback, pattern=f"^{UPDATE_PROJECT_PREFIX}"),
            CommandHandler('updateproject', my_projects_command)
        ],
        states={
            SELECT_PROJECT: [CallbackQueryHandler(select_project_for_update, pattern=f"^{SELECT_PROJECT_PREFIX}")],
            UPDATE_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_progress_state)],
            UPDATE_BLOCKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_blockers_state)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )
    application.add_handler(update_project_conv)

    # Simple Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("myprojects", my_projects_command))

    # View Project Handler
    application.add_handler(CallbackQueryHandler(view_project_action_callback, pattern=f"^{VIEW_PROJECT_PREFIX}"))

    logger.info("All bot handlers have been configured.")

async def start_command(update: object, context: object) -> None:
    """Handle the /start command."""
    if not hasattr(update, 'effective_user') or not hasattr(update, 'message'):
        return
    
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
    except Exception as e:
        logger.error(f"Error sending /start message: {e}", exc_info=True)

async def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Set up handlers
    setup_handlers(application)
    
    # Set commands
    await set_commands(application)
    
    # Start the bot
    if USE_LONG_POLLING:
        logger.info("Starting bot with long polling...")
        await application.run_polling()
    else:
        logger.info("Starting bot with webhook...")
        # Webhook setup will be handled by the webhook server
        await application.initialize()
        await application.start()
        await application.run_webhook(
            listen='0.0.0.0',
            port=int(os.getenv('PORT', 10000)),
            webhook_url=os.getenv('WEBHOOK_URL')
        )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot stopped due to error: {e}", exc_info=True) 