from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from app import get_user_projects_from_airtable, get_project_updates_from_airtable, format_project_summary_text, UPDATE_PROJECT_PREFIX

async def handle_project_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    project_id = query.data.split('_')[-1]
    projects = await get_user_projects_from_airtable(str(update.effective_user.id))
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    if not selected_project:
        await query.edit_message_text("❌ Error: Project not found. Please try /myprojects again.")
        return ConversationHandler.END
    project_summary = await format_project_summary_text(selected_project['fields'])
    updates = await get_project_updates_from_airtable(project_id)
    updates_text = "\n\n*Recent Updates:*\n"
    if updates:
        for update_record in updates[:3]:
            fields = update_record['fields']
            updates_text += f"\n📅 {fields.get('Timestamp', 'No date')}\nProgress: {fields.get('Update', 'No update')}\n"
            if fields.get('Blockers'):
                updates_text += f"Blockers: {fields['Blockers']}\n"
    else:
        updates_text += "\nNo updates yet."
    keyboard = [[
        InlineKeyboardButton("📝 Update Project", callback_data=f"{UPDATE_PROJECT_PREFIX}{project_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"{project_summary}{updates_text}", reply_markup=reply_markup, parse_mode='Markdown')
    return ConversationHandler.END 