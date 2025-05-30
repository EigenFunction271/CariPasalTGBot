from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app import get_user_projects_from_airtable, UPDATE_PROJECT_PREFIX, VIEW_PROJECT_PREFIX

async def my_projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    projects = await get_user_projects_from_airtable(user_id)
    if not projects:
        await update.message.reply_text("You don't have any projects yet. Use /newproject to create one!")
        return
    message = "Here are your projects:\n\n"
    keyboard = []
    for i, project in enumerate(projects, 1):
        fields = project['fields']
        project_id = project['id']
        message += f"{i}. {fields.get('Project Name', 'Unnamed Project')}\n   Status: {fields.get('Status', 'N/A')}\n   {fields.get('One-liner', '')}\n\n"
        keyboard.append([
            InlineKeyboardButton(f"📝 Update {fields.get('Project Name', 'Project')}", callback_data=f"{UPDATE_PROJECT_PREFIX}{project_id}"),
            InlineKeyboardButton(f"👁 View {fields.get('Project Name', 'Project')}", callback_data=f"{VIEW_PROJECT_PREFIX}{project_id}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown') 