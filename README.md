# Loophole Hackers Project Tracker Bot

A Telegram bot for Loophole Hackers community members to track and update their project progress. The bot syncs project data with Airtable automatically.

## Features

- `/newproject` - Create a new project entry
- `/updateproject` - Log progress updates for existing projects
- `/myprojects` - View and manage your projects
- `/searchprojects` - Search for projects by keyword, stack, or status
- Weekly digest of project updates (automated)

## Project Structure

```
.
├── app.py              # Main Flask application and Telegram bot setup
├── airtable_client.py  # Airtable API interaction module
├── weekly_digest.py    # Weekly project digest generator
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (create this)
├── .gitignore         # Git ignore rules
└── documentation/     # Project documentation
    ├── prd.md        # Product Requirements Document
    └── prd_v2        # Updated PRD with implementation details
```

## Prerequisites

- Python 3.8 or higher
- A Telegram account
- An Airtable account
- A Render account (for deployment)
- Git (for version control)

## Setup Guide

### 1. Local Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd loophole-project-tracker
   ```

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Telegram Bot Setup

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Start a chat and send `/newbot`
3. Follow the prompts to:
   - Choose a name for your bot (e.g., "Loophole Project Tracker")
   - Choose a username (must end in 'bot', e.g., "loophole_project_tracker_bot")
4. BotFather will give you a token. Save this for later.

5. Set up the group and topic for weekly digests:
   - Create a new **group** in Telegram (or use an existing one)
   - Add your bot as an administrator to the group
   - Make sure the bot has permission to post messages and manage topics
   - Enable topics (group must be a "forum" type group; see group settings)
   - Create a topic (thread) in the group for digests (e.g., "Project Updates")
   - Get the group ID and topic (thread) ID:
     
     **How to get the group ID:**
     - Add your bot to the group as an admin
     - Send any message in the group
     - Go to https://web.telegram.org/a/ and open the group
     - The URL will look like: `https://web.telegram.org/a/#-1001234567890`
     - The number after `#` is your group ID (include the `-100` prefix)
     - Alternatively, forward a message from the group to [@getidsbot](https://t.me/getidsbot) and it will reply with the group ID

     **How to get the topic (thread) ID:**
     - In the Telegram desktop app, right-click the topic and select "Copy Link"
     - The link will look like: `https://t.me/c/1234567890/456` (where `456` is the topic ID)
     - Or, in the mobile app, open the topic and tap the topic name, then tap "Copy Link"
     - The topic (thread) ID is the number after the last `/` in the link
     - Example: For `https://t.me/c/1234567890/456`, the topic ID is `456`

   - Save these IDs for your `.env` file

   - **.env example for group topic:**
     ```env
     TELEGRAM_BOT_TOKEN=your_bot_token_here
     TELEGRAM_DIGEST_CHAT_ID=-1001234567890  # Group ID (with -100 prefix)
     TELEGRAM_DIGEST_TOPIC_ID=456            # Topic (thread) ID
     ```

   - **Note:**
     - The bot must be an admin in the group and have permission to post in the topic
     - If you change the topic, update the `TELEGRAM_DIGEST_TOPIC_ID` in your `.env`
     - For private groups, you must use the `-100` prefix for the group ID

### 2.3. Setting the Telegram Webhook (Windows/PowerShell)

If your bot is not receiving updates, you may need to set the webhook manually. This is especially important if you are deploying on Render or using Windows, where the built-in PowerShell `curl` does not support the `-F` flag.

**How to set the webhook:**

- **Option 1: Use `curl.exe` (the real curl, if installed):**
  ```powershell
  curl.exe -F "url=https://caripasaltgbot.onrender.com/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
  ```

- **Option 2: Use PowerShell's `Invoke-RestMethod`:**
  ```powershell
  Invoke-RestMethod -Uri "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" -Method Post -Body @{ url = "https://caripasaltgbot.onrender.com/webhook" }
  ```

- **Option 3: Use Git Bash or WSL:**
  ```bash
  curl -F "url=https://caripasaltgbot.onrender.com/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
  ```

**After setting the webhook, verify it:**
```powershell
Invoke-RestMethod -Uri "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```
The `"url"` should end with `/webhook`.

---

### Troubleshooting: Webhook Not Working
- If Telegram is POSTing to `/` (root) and you see 404s in your logs, your webhook is not set to `/webhook`.
- Always check the webhook URL with `getWebhookInfo` after deployment.
- If your code is supposed to set the webhook but it doesn't update, set it manually as above.
- On Windows, always use `curl.exe` or `Invoke-RestMethod` instead of the PowerShell alias for `curl`.

### 3. Airtable Setup

1. Create a new Airtable base:
   - Go to [Airtable](https://airtable.com)
   - Click "Add a base" → "Start from scratch"
   - Name it "Loophole Project Tracker"

2. Create two tables:

   **Projects Table**
   | Field             | Type           | Notes                                    |
   |------------------|----------------|------------------------------------------|
   | Project Name      | Text           | Single line text                         |
   | Owner Telegram ID | Text           | Single line text                         |
   | One-liner         | Text           | Single line text                         |
   | Problem Statement | Long text      | Multiple lines allowed                   |
   | Stack             | Text           | Single line text                         |
   | GitHub/Demo       | URL            | Must be valid URL                        |
   | Status            | Single select  | Options: Idea, MVP, Launched            |
   | Help Needed       | Long text      | Multiple lines allowed                   |
   | Last Updated      | Date           | Auto-generated                           |

   **Updates Table**
   | Field             | Type           | Notes                                    |
   |------------------|----------------|------------------------------------------|
   | Project          | Link to Project| Link to Projects table                   |
   | Update           | Long text      | Multiple lines allowed                   |
   | Blockers         | Long text      | Multiple lines allowed                   |
   | Updated By       | Text           | Telegram ID                              |
   | Timestamp        | Date           | Auto-generated                           |

3. Create a Personal Access Token:
   - Go to your [Airtable account page](https://airtable.com/account)
   - Click on "API" in the left sidebar
   - Under "Personal access tokens", click "Create a token"
   - Fill in the token details:
     - Name: "Loophole Project Tracker"
     - Expiration: Choose based on your needs (e.g., 1 year)
     - Scopes: Select:
       - `data.records:read`
       - `data.records:write`
       - `schema.bases:read`
   - Click "Create token"
   - **IMPORTANT**: Copy the token immediately! It will look like `patXXXXXXXXXXXXXX`
     - You won't be able to see it again after leaving the page
     - Store it securely (e.g., in a password manager)

4. Get your Base ID:
   - Open your base
   - The URL will be like: `https://airtable.com/appXXXXXXXXXXXXXX/tblYYYYYYYYYYYYYY`
   - The `appXXXXXXXXXXXXXX` part is your Base ID

5. Test your token (optional but recommended):
   ```bash
   # Windows PowerShell
   $headers = @{
       "Authorization" = "Bearer patXXXXXXXXXXXXXX"
   }
   Invoke-RestMethod -Uri "https://api.airtable.com/v0/meta/bases/appXXXXXXXXXXXXXX/tables" -Headers $headers

   # macOS/Linux
   curl -H "Authorization: Bearer patXXXXXXXXXXXXXX" \
        https://api.airtable.com/v0/meta/bases/appXXXXXXXXXXXXXX/tables
   ```

### 4. Environment Setup

1. Create a `.env` file in the project root:
   ```env
   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_bot_token_here  # From BotFather
   TELEGRAM_DIGEST_CHAT_ID=-100xxxxxxxxxx  # Channel ID from @userinfobot

   # Airtable Configuration
   AIRTABLE_API_KEY=patXXXXXXXXXXXXXX      # Your Personal Access Token
   AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX      # Your Base ID
   AIRTABLE_PROJECTS_TABLE_NAME=Projects    # Name of your Projects table
   AIRTABLE_UPDATES_TABLE_NAME=Updates      # Name of your Updates table

   # Webhook URL (for production)
   WEBHOOK_URL=https://your-app-name.onrender.com

   # Port (for local development)
   PORT=5000
   ```

2. Verify your environment variables:
   ```bash
   # Check if all required variables are set
   python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('TELEGRAM_BOT_TOKEN:', bool(os.getenv('TELEGRAM_BOT_TOKEN'))); print('TELEGRAM_DIGEST_CHAT_ID:', bool(os.getenv('TELEGRAM_DIGEST_CHAT_ID'))); print('AIRTABLE_API_KEY:', bool(os.getenv('AIRTABLE_API_KEY'))); print('AIRTABLE_BASE_ID:', bool(os.getenv('AIRTABLE_BASE_ID'))); print('AIRTABLE_PROJECTS_TABLE_NAME:', bool(os.getenv('AIRTABLE_PROJECTS_TABLE_NAME'))); print('AIRTABLE_UPDATES_TABLE_NAME:', bool(os.getenv('AIRTABLE_UPDATES_TABLE_NAME')))"
   ```

### 5. Local Testing

1. Start the bot:
   ```bash
   python app.py
   ```

2. Test the bot:
   - Open Telegram
   - Search for your bot
   - Start a chat
   - Try the commands:
     - `/start` - Should show welcome message
     - `/newproject` - Should start project creation flow
     - `/myprojects` - Should show your projects (empty at first)
     - `/searchprojects` - Should start project search flow

3. Test the weekly digest:
   ```bash
   python weekly_digest.py
   ```

### 6. Deployment on Render

1. Create a new Web Service on Render:
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" and select "Web Service"
   - Connect your GitHub repository

2. Configure the service:
   - Name: `loophole-project-tracker` (or your preferred name)
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:application`
   - Plan: Free (or your preferred plan)

3. Add Environment Variables:
   - Go to the "Environment" tab
   - Add all variables from your `.env` file
   - For `WEBHOOK_URL`, use your Render URL: `https://your-app-name.onrender.com`

4. Deploy:
   - Click "Create Web Service"
   - Wait for the first deployment to complete

5. Keep the service alive:
   - Render's free tier puts services to sleep after 15 minutes of inactivity
   - Use [UptimeRobot](https://uptimerobot.com/) to ping your service:
     - Create a free account
     - Add a new monitor:
       - Monitor Type: HTTP(s)
       - URL: Your Render URL + `/ping`
       - Monitoring Interval: 5 minutes

6. Set up weekly digest:
   - Create a new Cron Job on Render
   - Schedule: Weekly (e.g., every Monday at 9 AM UTC)
   - Command: `python weekly_digest.py`

## Development

### Code Structure

- `app.py`: Main Flask application and Telegram bot setup
- `airtable_client.py`: Airtable API interaction module
- `weekly_digest.py`: Weekly project digest generator
- `requirements.txt`: Python dependencies
- `.env`: Environment variables (not in git)
- `documentation/`: Project documentation

### Key Features

- Asynchronous request handling
- Comprehensive error logging
- Input validation and sanitization
- Modular command handler structure
- Weekly project digest generation
- Project search functionality

### Testing

Run tests with pytest:
```bash
pytest
```

### Code Style

Format code with black:
```bash
black .
```

Check code style with flake8:
```bash
flake8 .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Add your license here] 

## Deployment Bugs & Fixes Log

### 1. ImportError: cannot import name 'Filters' from 'telegram.ext'
- **Cause:** `python-telegram-bot` v20+ changed `Filters` to `filters` (lowercase, as a module).
- **Fix:**
  - Change all imports and usages from `Filters` to `filters`.
  - Example: `from telegram.ext import filters` and `filters.TEXT & ~filters.COMMAND`.

### 2. ImportError: cannot import name 'FIELD' from 'pyairtable.formulas'
- **Cause:** The `FIELD` function is only available in `pyairtable` v2.2.0+.
- **Fix:**
  - Ensure `pyairtable>=2.2.0` in `requirements.txt`.
  - Reinstall dependencies and redeploy.

### 3. Webhook set to root URL instead of `/webhook`
- **Symptom:** Telegram POSTs to `/` (root), logs show 404s, and `getWebhookInfo` shows the root URL.
- **Cause:** Webhook was not set to `/webhook`.
- **Fix:**
  - Manually set the webhook using:
    - `curl.exe -F "url=https://your-app.onrender.com/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook`
    - Or PowerShell: `Invoke-RestMethod -Uri "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" -Method Post -Body @{ url = "https://your-app.onrender.com/webhook" }`
  - Always verify with `getWebhookInfo`.

### 4. PowerShell curl does not support `-F` flag
- **Symptom:** `curl -F ...` fails with `ParameterBindingException` in PowerShell.
- **Cause:** PowerShell's `curl` is an alias for `Invoke-WebRequest`, which does not support `-F`.
- **Fix:**
  - Use `curl.exe` (the real curl), or use `Invoke-RestMethod` as shown above.

### 5. RuntimeWarning: coroutine 'Queue.put' was never awaited
- **Symptom:** Warning in logs: `coroutine 'Queue.put' was never awaited`.
- **Cause:** In `python-telegram-bot` v20+, `update_queue.put` is async and must be awaited.
- **Fix:**
  - Change the Flask `/webhook` route to `async def` and use `await telegram_app.update_queue.put(update)`.
  - Note: Flask async support may require a compatible server (e.g., Quart or FastAPI for full async).

### 6. 404s for `/` (root) in logs
- **Symptom:** Logs show repeated 404s for `/`.
- **Cause:** No route is defined for `/` in Flask app. This is normal unless you want a homepage.
- **Fix:**
  - Ignore, or add a root route if desired:
    ```python
    @flask_app.route('/')
    def home():
        return 'Loophole Bot is running!', 200
    ``` 