# weekly_digest.py
import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode

# Assuming airtable_client.py is in the same directory or accessible via PYTHONPATH
import airtable_client

def format_digest_message(new_projects, recent_updates_by_project):
    """Formats the weekly digest message."""
    message_parts = ["*Weekly Project Digest!*\n\n"]

    if new_projects:
        message_parts.append("*New Projects This Week:*\n")
        for project in new_projects:
            fields = project.get('fields', {})
            name = fields.get("Project Name", "N/A")
            one_liner = fields.get("One-liner", "")
            message_parts.append(f"- *{name}*: {one_liner}\n")
        message_parts.append("\n")
    else:
        message_parts.append("No new projects this week.\n\n")

    if recent_updates_by_project:
        message_parts.append("*Recent Updates:*\n")
        for project_name, updates in recent_updates_by_project.items():
            message_parts.append(f"*{project_name}:*\n")
            for update_text in updates:
                # Limit length of update text if necessary
                summary = (update_text[:150] + '...') if len(update_text) > 150 else update_text
                message_parts.append(f"  - {summary}\n")
            message_parts.append("\n")
    else:
        message_parts.append("No specific project updates logged this week.\n")
    
    message_parts.append("Remember to update your progress via the bot! `/updateproject`")
    return "".join(message_parts)

async def send_digest(bot: Bot, chat_id: str, message_thread_id: int | None, message: str):
    """Send the digest message to the specified chat and topic."""
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            message_thread_id=message_thread_id
        )
        print("Weekly digest sent successfully.")
    except Exception as e:
        print(f"Error sending weekly digest: {e}")
        raise

async def main():
    load_dotenv()

    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_DIGEST_CHAT_ID = os.getenv('TELEGRAM_DIGEST_CHAT_ID')
    TELEGRAM_DIGEST_TOPIC_ID = os.getenv('TELEGRAM_DIGEST_TOPIC_ID')

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_DIGEST_CHAT_ID:
        print("Error: TELEGRAM_BOT_TOKEN or TELEGRAM_DIGEST_CHAT_ID not set in .env")
        return

    # Convert topic ID to int if it's set, otherwise None
    message_thread_id_for_digest = int(TELEGRAM_DIGEST_TOPIC_ID) if TELEGRAM_DIGEST_TOPIC_ID else None

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    print(f"Fetching updates since {one_week_ago.isoformat()}")
    recent_raw_updates = airtable_client.get_updates_since(one_week_ago)
    
    updates_by_project = {}
    if recent_raw_updates:
        for update_record in recent_raw_updates:
            fields = update_record.get('fields', {})
            project_link_field = fields.get("Project (Linked)")
            
            if not project_link_field:
                print(f"Skipping update {update_record.get('id')} as it's not linked to a project.")
                continue
            
            project_record_id = project_link_field[0]
            project_name = airtable_client.get_project_name_from_id(project_record_id)
            update_text = fields.get("Update Text", "No details.")
            
            if project_name not in updates_by_project:
                updates_by_project[project_name] = []
            updates_by_project[project_name].append(update_text)

    newly_created_projects = [] # Placeholder

    digest_message = format_digest_message(newly_created_projects, updates_by_project)
    
    if not digest_message.strip() or (not updates_by_project and not newly_created_projects):
        print("No new projects or significant updates found for the weekly digest. No message sent.")
        return

    print(f"Sending digest to chat ID: {TELEGRAM_DIGEST_CHAT_ID}, Topic ID: {message_thread_id_for_digest}")
    await send_digest(bot, TELEGRAM_DIGEST_CHAT_ID, message_thread_id_for_digest, digest_message)

if __name__ == '__main__':
    asyncio.run(main())