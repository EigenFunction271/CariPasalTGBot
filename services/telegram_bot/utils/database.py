# utils/database.py
import os
import sys
from typing import Dict, Any, List, Optional
from pyairtable import Api, Table
from services.telegram_bot.utils.constants import logger

# --- Airtable Configuration & Validation ---
REQUIRED_ENV_VARS = [
    'AIRTABLE_API_KEY',
    'AIRTABLE_BASE_ID',
]

# Log presence of environment variables
for var_name in REQUIRED_ENV_VARS:
    logger.info(f"ENV_CHECK: {var_name} present: {var_name in os.environ}")

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    critical_message = f"CRITICAL STARTUP FAILURE: Missing required environment variables: {', '.join(missing_vars)}"
    logger.critical(critical_message)
    sys.exit(critical_message)

# Get validated environment variables
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY', '')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID', '')

# Validate Airtable API key format
if not AIRTABLE_API_KEY.startswith('pat'):
    critical_message = "CRITICAL STARTUP FAILURE: Invalid Airtable API key format. Must start with 'pat'."
    logger.critical(critical_message)
    sys.exit(critical_message)

# Initialize Airtable client
try:
    airtable_api = Api(AIRTABLE_API_KEY)
    airtable_base = airtable_api.base(AIRTABLE_BASE_ID)
    projects_table: Table = airtable_base.table('Ongoing projects')
    updates_table: Table = airtable_base.table('Updates')
    projects_table.all(max_records=1)  # Test connection
    logger.info("Successfully connected to Airtable and verified table access.")
except Exception as e:
    critical_message = f"CRITICAL STARTUP FAILURE: Failed to initialize Airtable client or access tables: {e}"
    logger.critical(critical_message, exc_info=True)
    sys.exit(critical_message)

# --- Helper Functions ---
async def get_user_projects_from_airtable(user_id: str) -> List[Dict[str, Any]]:
    """Fetches all projects for a given Telegram user ID from Airtable."""
    try:
        formula = f"{{Owner Telegram ID}}='{user_id}'"
        records = projects_table.all(formula=formula, sort=[{'field': 'Project Name', 'direction': 'asc'}])
        logger.info(f"Fetched {len(records)} projects for user {user_id}.")
        return records
    except Exception as e:
        logger.error(f"Airtable error fetching projects for User ID {user_id}: {e}", exc_info=True)
        return []

async def get_project_updates_from_airtable(project_airtable_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Fetches recent updates for a specific project ID from Airtable."""
    try:
        formula = f"{{Project}}='{project_airtable_id}'"
        records = updates_table.all(formula=formula, sort=[{"field": "Timestamp", "direction": "desc"}], max_records=limit)
        logger.info(f"Fetched {len(records)} updates for project {project_airtable_id}.")
        return records
    except Exception as e:
        logger.error(f"Airtable error fetching updates for Project ID {project_airtable_id}: {e}", exc_info=True)
        return []

async def format_project_summary_text(project_fields: Dict[str, Any]) -> str:
    """Formats a project's details into a readable string for Telegram messages."""
    def get_field(name: str, default_value: str = "N/A") -> str:
        return project_fields.get(name, default_value) or default_value

    summary = (
        f"📋 *{get_field('Project Name')}*\n"
        f"_{get_field('One-liner', 'No tagline provided.')}_\n\n"
        f"*Status:* {get_field('Status')}\n"
        f"*Tech Stack:* {get_field('Stack', 'Not specified.')}\n"
        f"*Help Needed:* {get_field('Help Needed', 'None specified.')}\n"
        f"*GitHub/Demo Link:* {get_field('GitHub/Demo', 'No link provided.')}"
    )
    return summary 