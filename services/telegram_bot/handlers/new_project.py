from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import asyncio
from utils.constants import (
    PROJECT_NAME, PROJECT_TAGLINE, PROBLEM_STATEMENT, TECH_STACK, GITHUB_LINK, PROJECT_STATUS, HELP_NEEDED,
    STATUS_OPTIONS, MAX_PROJECT_NAME_LENGTH, MAX_TAGLINE_LENGTH, MAX_PROBLEM_STATEMENT_LENGTH, MAX_TECH_STACK_LENGTH, MAX_GITHUB_LINK_LENGTH, MAX_HELP_NEEDED_LENGTH,
    validate_input_text, logger
)
from utils.database import projects_table

async def newproject_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /newproject command."""
    await update.message.reply_text("Let's create a new project! 🚀\n\nWhat's the name of your project?")
    return PROJECT_NAME

async def project_name_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        name = validate_input_text(update.message.text, "Project name", MAX_PROJECT_NAME_LENGTH)
        context.user_data['project_name'] = name
        current_loop = asyncio.get_event_loop()
        logger.info(f"PROJECT_NAME_STATE: Current loop: {current_loop}, is_closed: {current_loop.is_closed()}, is_running: {current_loop.is_running()}")

        await update.message.reply_text("Great! Now, give me a one-liner tagline for your project:")
        return PROJECT_TAGLINE
    except Exception as e:
        current_loop_on_exc = asyncio.get_event_loop()
        logger.error(
            f"PROJECT_NAME_STATE: Error: {e}. Loop: {current_loop_on_exc}, is_closed: {current_loop_on_exc.is_closed()}, is_running: {current_loop_on_exc.is_running()}", 
            exc_info=True
        )
        return PROJECT_NAME

async def project_tagline_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        tagline = validate_input_text(update.message.text, "Tagline", MAX_TAGLINE_LENGTH)
        context.user_data['tagline'] = tagline
        await update.message.reply_text("What problem does your project solve? Please provide a brief problem statement:")
        return PROBLEM_STATEMENT
    except Exception as e:
        await update.message.reply_text(str(e))
        return PROJECT_TAGLINE

async def problem_statement_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        statement = validate_input_text(update.message.text, "Problem statement", MAX_PROBLEM_STATEMENT_LENGTH)
        context.user_data['problem_statement'] = statement
        await update.message.reply_text("What technologies are you using? List your tech stack:")
        return TECH_STACK
    except Exception as e:
        await update.message.reply_text(str(e))
        return PROBLEM_STATEMENT

async def tech_stack_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        stack = validate_input_text(update.message.text, "Tech stack", MAX_TECH_STACK_LENGTH)
        context.user_data['tech_stack'] = stack
        await update.message.reply_text("Do you have a GitHub repository or demo link? Please share it:")
        return GITHUB_LINK
    except Exception as e:
        await update.message.reply_text(str(e))
        return TECH_STACK

async def github_link_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        link = validate_input_text(update.message.text, "GitHub/Demo link", MAX_GITHUB_LINK_LENGTH, can_be_empty=True)
        context.user_data['github_link'] = link
        keyboard = [[InlineKeyboardButton(status, callback_data=status)] for status in STATUS_OPTIONS]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("What's the current status of your project?", reply_markup=reply_markup)
        return PROJECT_STATUS
    except Exception as e:
        await update.message.reply_text(str(e))
        return GITHUB_LINK

async def project_status_state_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['status'] = query.data
    await query.edit_message_text("Finally, what kind of help do you need? (e.g., technical expertise, design, marketing)")
    return HELP_NEEDED

async def help_needed_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        help_needed = validate_input_text(update.message.text, "Help needed", MAX_HELP_NEEDED_LENGTH, can_be_empty=True)
        context.user_data['help_needed'] = help_needed
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
        projects_table.create(project_data)
        await update.message.reply_text("🎉 Your project has been created successfully!\n\nYou can use /myprojects to view your projects.")
    except Exception as e:
        logger.error(f"Error saving project: {e}")
        await update.message.reply_text("❌ Sorry, there was an error saving your project. Please try again later.")
        return HELP_NEEDED
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END 