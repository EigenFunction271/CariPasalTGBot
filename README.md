# Loophole Hackers Project Tracker Bot

A Telegram bot for Loophole Hackers community members to track and update their project progress. The bot syncs project data with Airtable automatically.

## Features

- `/newproject` - Create a new project entry
- `/updateproject` - Log progress updates for existing projects
- `/myprojects` - View and manage your projects

## Project Structure

```
.
├── app.py              # Main Flask application and Telegram bot setup
├── constants.py        # Shared constants, logging config, and utilities
├── gunicorn_config.py  # Gunicorn server configuration
├── ping_service.py     # Service to keep the bot alive on Render
├── requirements.txt    # Python dependencies
├── handlers/          # Telegram bot command handlers
│   ├── myprojects.py  # /myprojects command handler
│   ├── new_project.py # /newproject command handler
│   ├── update_project.py # /updateproject command handler
│   └── view_project.py # Project viewing functionality
└── documentation/     # Project documentation
    ├── prd.md        # Product Requirements Document
    └── todo.md       # Development TODO list
```

## Prerequisites

- Python 3.8 or higher
- A Telegram account
- An Airtable account
- A Render account (for deployment)

## Setup Guide

### 1. Local Development Setup

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

### 2. Telegram Bot Setup

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Start a chat and send `/newbot`
3. Follow the prompts to:
   - Choose a name for your bot
   - Choose a username (must end in 'bot')
4. BotFather will give you a token. Save this for later.

### 3. Airtable Setup

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

### 4. Webhook Setup

1. For local development, you'll need a public URL. You can use [ngrok](https://ngrok.com/):
   ```bash
   # Install ngrok
   # Then run:
   ngrok http 5000
   ```
   This will give you output like:
   ```
   Forwarding    https://xxxx-xx-xx-xxx-xx.ngrok-free.app -> http://localhost:5000
   ```
   Use the `https://xxxx-xx-xx-xxx-xx.ngrok-free.app` URL as your `WEBHOOK_URL` in the `.env` file.

2. For production, you'll use your Render URL (see Deployment section)

### 5. Environment Variables

Create a `.env` file in the project root:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
AIRTABLE_API_KEY=your_airtable_personal_access_token
AIRTABLE_BASE_ID=your_airtable_base_id
WEBHOOK_URL=your_webhook_url
PORT=5000
```

> **Note**: The `AIRTABLE_API_KEY` environment variable name remains the same for compatibility, but it should contain your Personal Access Token, not an API key.

### 5. Local Testing

1. Start the bot:
   ```bash
   python app.py
   ```

2. Test the bot:
   - Open Telegram
   - Search for your bot
   - Start a chat
   - Try the commands: `/start`, `/newproject`, `/myprojects`

### 6. Deployment on Render

1. Create a new Web Service on Render:
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" and select "Web Service"
   - Connect your GitHub repository

2. Configure the service:
   - Name: `loophole-project-tracker` (or your preferred name)
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn -c gunicorn_config.py app:app`
   - Plan: Free (or your preferred plan)

3. Add Environment Variables:
   - Go to the "Environment" tab
   - Add all variables from your `.env` file
   - For `WEBHOOK_URL`, use your Render URL: `https://your-app-name.onrender.com`

4. Deploy:
   - Click "Create Web Service"
   - Wait for the first deployment to complete

5. Set up the webhook:
   - Once deployed, your bot will be available at your Render URL
   - The webhook will be automatically set up when the bot starts

The free tier of Render puts services to sleep after 15 minutes of inactivity. To prevent this, you can use one of these methods:

1. View logs:
   - On Render: Go to your service → Logs
   - Locally: Check `bot.log`

2. Common issues:
   - If the bot stops responding, check the logs
   - If Airtable sync fails, verify your API key and base ID
   - If webhook fails, ensure your Render service is running

3. Keeping the service alive on Render:
   - Render's free tier puts services to sleep after 15 minutes of inactivity
   - To prevent this, you can use one of these free services:

   a) **UptimeRobot** (Recommended):
      - Go to [UptimeRobot](https://uptimerobot.com/)
      - Sign up for a free account
      - Add a new monitor:
        - Monitor Type: HTTP(s)
        - Friendly Name: "Loophole Bot Ping"
        - URL: Your Render URL + `/ping` (e.g., `https://your-app.onrender.com/ping`)
        - Monitoring Interval: 5 minutes
      - The free tier includes 50 monitors and 5-minute intervals

   b) **Cron-job.org**:
      - Go to [Cron-job.org](https://cron-job.org/)
      - Sign up for a free account
      - Create a new cronjob:
        - URL: Your Render URL + `/ping`
        - Schedule: Every 14 minutes
        - Request Method: GET
      - The free tier includes unlimited cronjobs

   c) **Local Ping Service** (Alternative):
      - If you prefer to run your own ping service:
        ```bash
        # Install the ping service requirements
        pip install requests python-dotenv

        # Run the ping service
        python ping_service.py
        ```
      - The ping service will:
        - Send a request to your bot every 14 minutes
        - Log all ping attempts to `ping_service.log`
        - Keep your bot active 24/7
      - You can run this on:
        - Your local machine
        - A Raspberry Pi
        - Another always-on server

   > **Note**: UptimeRobot is recommended as it's reliable, free, and requires no setup on your part. It also provides monitoring and alerts if your service goes down.

## Development

### Code Structure

- `app.py`: Main Flask application and Telegram bot setup
- `constants.py`: Shared constants, logging configuration, and utility functions
- `handlers/`: Telegram bot command handlers
  - `myprojects.py`: Handles `/myprojects` command
  - `new_project.py`: Handles `/newproject` command
  - `update_project.py`: Handles `/updateproject` command
  - `view_project.py`: Handles project viewing functionality
- `gunicorn_config.py`: Gunicorn server configuration
- `ping_service.py`: Service to keep the bot alive on Render

### Key Features

- Asynchronous request handling with gevent
- Lazy initialization of Telegram bot instance
- Graceful shutdown handling
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