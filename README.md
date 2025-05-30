# Loophole Hackers Project Tracker Bot

A Telegram bot for Loophole Hackers community members to track and update their project progress. The bot syncs project data with Airtable automatically.

## Features

- `/newproject` - Create a new project entry
- `/updateproject` - Log progress updates for existing projects
- `/myprojects` - View and manage your projects

## Project Structure

```
.
├── services/                # Split services
│   ├── telegram_bot/        # Bot service
│   │   ├── utils/          # Shared utilities
│   │   │   ├── __init__.py
│   │   │   ├── constants.py # Shared constants and logging config
│   │   │   └── database.py  # Airtable integration
│   │   ├── bot.py          # Main bot logic
│   │   └── handlers/       # Command handlers
│   │       ├── myprojects.py
│   │       ├── new_project.py
│   │       ├── update_project.py
│   │       └── view_project.py
│   └── webhook_server/      # Webhook service
│       ├── app.py          # Flask webhook server
│       └── gunicorn_config.py
├── requirements.txt         # Project dependencies
└── documentation/          # Project documentation
    ├── prd.md             # Product Requirements Document
    ├── testing_plan.md    # Testing documentation
    └── updates.md         # Recent updates and changes
```

## Prerequisites

- Python 3.8 or higher
- A Telegram account
- An Airtable account
- A Render account (for deployment)

## Setup Guide

### 1. Telegram Bot Setup

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Start a chat and send `/newbot`
3. Follow the prompts to:
   - Choose a name for your bot
   - Choose a username (must end in 'bot')
4. BotFather will give you a token. Save this for later.

### 2. Airtable Setup

1. Create a new Airtable base
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
     - Name: "Loophole Project Tracker" (or your preferred name)
     - Expiration: Choose based on your needs (e.g., 1 year)
     - Scopes: Select the following:
       - `data.records:read` (to read project and update records)
       - `data.records:write` (to create and update records)
       - `schema.bases:read` (to read base structure)
   - Click "Create token"
   - **IMPORTANT**: Copy the token immediately! It will look like `patXXXXXXXXXXXXXX`
     - You won't be able to see it again after leaving the page
     - Store it securely (e.g., in a password manager)
     - You'll need it for the `.env` file

   > **Note**: Airtable is deprecating API keys in favor of Personal Access Tokens. API keys will stop working after January 2024. This setup uses the new Personal Access Token system.

4. Get your Base ID:
   - Open your base
   - The URL will be like: `https://airtable.com/appXXXXXXXXXXXXXX/tblYYYYYYYYYYYYYY`
   - The `appXXXXXXXXXXXXXX` part is your Base ID

5. Test your token (optional but recommended):
   - Open a terminal
   - For Windows PowerShell, run:
     ```powershell
     $headers = @{
         "Authorization" = "Bearer patXXXXXXXXXXXXXX"
     }
     Invoke-RestMethod -Uri "https://api.airtable.com/v0/meta/bases/appXXXXXXXXXXXXXX/tables" -Headers $headers
     ```
   - For Unix-like systems (Linux/Mac), run:
     ```bash
     curl -H "Authorization: Bearer patXXXXXXXXXXXXXX" \
          https://api.airtable.com/v0/meta/bases/appXXXXXXXXXXXXXX/tables
     ```
   - If successful, you'll see a JSON response with your tables
   - If you get an error, double-check your token and base ID

### 3. Local Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd loophole-project-tracker
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root:
   ```env
   # Bot Service
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   USE_LONG_POLLING=true  # Set to false when using webhook
   PORT=10001  # Bot service port

   # Webhook Server
   BOT_SERVICE_URL=http://localhost:10001  # URL of bot service
   WEBHOOK_PORT=10000  # Webhook server port

   # Airtable
   AIRTABLE_API_KEY=your_airtable_personal_access_token
   AIRTABLE_BASE_ID=your_airtable_base_id
   ```

### 4. Running the Services Locally

#### Bot Service
```bash
cd services/telegram_bot
python bot.py
```

#### Webhook Server
```bash
cd services/webhook_server
gunicorn -c gunicorn_config.py services.webhook_server.app:app
```

### 5. Local Testing with Webhooks

1. Install ngrok:
   ```bash
   # Windows (with scoop)
   scoop install ngrok
   
   # macOS (with homebrew)
   brew install ngrok
   
   # Linux
   snap install ngrok
   ```

2. Start ngrok:
   ```bash
   ngrok http 10000
   ```

3. Copy the HTTPS URL (e.g., `https://xxxx-xx-xx-xxx-xx.ngrok-free.app`)

4. Set up the webhook:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<NGROK_URL>
   ```

5. Test the bot:
   - Open Telegram
   - Search for your bot
   - Start a chat
   - Try the commands: `/start`, `/newproject`, `/myprojects`

### 6. Deployment on Render

1. Create a new Web Service for the Bot:
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" and select "Web Service"
   - Connect your GitHub repository
   - Configure the service:
     - Name: `loophole-project-tracker-bot`
     - Environment: `Python 3`
     - Build Command: `pip install -e . && pip install -r requirements.txt`
     - Start Command: `python -m services.telegram_bot.bot`
     - Plan: Free (or your preferred plan)
   - Add Environment Variables:
     - `TELEGRAM_BOT_TOKEN`
     - `USE_LONG_POLLING=false`
     - `PORT=10001`
     - `AIRTABLE_API_KEY`
     - `AIRTABLE_BASE_ID`

2. Create another Web Service for the Webhook Server:
   - Click "New +" and select "Web Service"
   - Connect the same GitHub repository
   - Configure the service:
     - Name: `loophole-project-tracker-webhook`
     - Environment: `Python 3`
     - Build Command: `pip install -e . && pip install -r requirements.txt`
     - Start Command: `gunicorn -c services/webhook_server/gunicorn_config.py services.webhook_server.app:app`
     - Plan: Free (or your preferred plan)
   - Add Environment Variables:
     - `TELEGRAM_BOT_TOKEN`
     - `BOT_SERVICE_URL=https://loophole-project-tracker-bot.onrender.com`
     - `PORT=10000`

3. Set up the webhook:
   - Once both services are deployed, set up the webhook:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://loophole-project-tracker-webhook.onrender.com
   ```

4. Keep the services alive:
   - Render's free tier puts services to sleep after 15 minutes of inactivity
   - Use [UptimeRobot](https://uptimerobot.com/) to ping the webhook server:
     - Monitor Type: HTTP(s)
     - URL: `https://loophole-project-tracker-webhook.onrender.com/health`
     - Monitoring Interval: 5 minutes

### 7. Monitoring and Maintenance

1. View logs:
   - On Render: Go to your service → Logs
   - Locally: Check `bot.log` and `webhook_server.log`

2. Common issues:
   - If the bot stops responding:
     - Check if both services are running
     - Verify webhook URL is set correctly
     - Check logs for errors
   - If Airtable sync fails:
     - Verify your Personal Access Token is valid
     - Check if the base ID is correct
     - Ensure tables are named correctly
   - If webhook fails:
     - Check if the webhook server is running
     - Verify the bot service URL is correct
     - Check if the services can communicate

## Development

### Code Structure

- `utils/`: Shared utilities used by both services
  - `constants.py`: Shared constants and logging configuration
  - `database.py`: Airtable integration code
- `services/`: Split services
  - `telegram_bot/`: Bot service with command handlers
  - `webhook_server/`: Webhook server for Telegram updates

### Key Features

- Split architecture for better scalability
- Asynchronous request handling
- Comprehensive error logging
- Input validation and sanitization
- Modular command handler structure

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Add your license here] 