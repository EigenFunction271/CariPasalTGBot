from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from app import (
    SELECT_PROJECT, UPDATE_PROGRESS, UPDATE_BLOCKERS,
    get_user_projects_from_airtable, get_project_updates_from_airtable, updates_table, logger
)

async def handle_project_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    project_id = query.data.split('_')[-1]
    context.user_data['selected_project_id'] = project_id
    await query.edit_message_text(f"Updating project. What progress have you made this week?")
    return UPDATE_PROGRESS

async def update_progress_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['progress'] = update.message.text
    await update.message.reply_text("Are there any blockers or challenges you're facing?")
    return UPDATE_BLOCKERS

async def update_blockers_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['blockers'] = update.message.text
    try:
        update_data = {
            'Project': [context.user_data['selected_project_id']],
            'Update': context.user_data['progress'],
            'Blockers': context.user_data['blockers'],
            'Updated By': str(update.effective_user.id),
        }
        updates_table.create(update_data)
        await update.message.reply_text("✅ Your project update has been saved successfully!\n\nYou can use /myprojects to view your projects or log another update.")
    except Exception as e:
        logger.error(f"Error saving update: {e}")
        await update.message.reply_text("❌ Sorry, there was an error saving your update. Please try again later.")
    context.user_data.clear()
    return ConversationHandler.END

async def select_project_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    project_id = query.data.split('_')[-1]
    context.user_data['selected_project_id'] = project_id
    await query.edit_message_text(f"Updating project. What progress have you made this week?")
    return UPDATE_PROGRESS 