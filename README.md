# Loophole Hackers Project Tracker Bot

A Telegram bot for Loophole Hackers community members to track and update their project progress. The bot syncs project data with Airtable automatically.

## Features

- `/newproject` - Create a new project entry
- `/updateproject` - Log progress updates for existing projects
- `/myprojects` - View and manage your projects

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   AIRTABLE_API_KEY=your_airtable_key
   AIRTABLE_BASE_ID=your_base_id
   WEBHOOK_URL=your_webhook_url
   ```
5. Run the application:
   ```bash
   python app.py
   ```

## Development

- Uses Flask for webhook handling
- Python-telegram-bot for Telegram integration
- PyAirtable for Airtable API interaction
- Deployed on Render

## Environment Variables

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather
- `AIRTABLE_API_KEY`: Your Airtable API key
- `AIRTABLE_BASE_ID`: Your Airtable base ID
- `WEBHOOK_URL`: The public URL where your bot is hosted 