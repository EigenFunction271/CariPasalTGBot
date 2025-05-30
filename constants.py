# constants.py
import os
import logging
import sys
from typing import Dict, Any, List, Optional

# --- Logging Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# --- Conversation States ---
PROJECT_NAME = 0
PROJECT_TAGLINE = 1
PROBLEM_STATEMENT = 2
TECH_STACK = 3
GITHUB_LINK = 4
PROJECT_STATUS = 5
HELP_NEEDED = 6

SELECT_PROJECT = 7
UPDATE_PROGRESS = 8
UPDATE_BLOCKERS = 9

# --- Constants ---
STATUS_OPTIONS = ['Idea', 'MVP', 'Launched']

# Callback data prefixes
UPDATE_PROJECT_PREFIX = "updateproject_"
VIEW_PROJECT_PREFIX = "viewproject_"
SELECT_PROJECT_PREFIX = "selectproject_"

# Max input lengths
MAX_PROJECT_NAME_LENGTH = 1000
MAX_TAGLINE_LENGTH = 2500
MAX_PROBLEM_STATEMENT_LENGTH = 5500
MAX_TECH_STACK_LENGTH = 5000
MAX_GITHUB_LINK_LENGTH = 300
MAX_HELP_NEEDED_LENGTH = 7500
MAX_UPDATE_LENGTH = 9000
MAX_BLOCKERS_LENGTH = 10000

# --- Custom Exceptions ---
class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass

# --- Helper Functions ---
def validate_input_text(text: str, field_name: str, max_length: int, can_be_empty: bool = False) -> str:
    """Validates text input: checks for emptiness (if not allowed) and max length."""
    processed_text = text.strip()
    if not can_be_empty and not processed_text:
        raise ValidationError(f"{field_name} cannot be empty. Please provide some text.")
    if len(processed_text) > max_length:
        raise ValidationError(
            f"{field_name} is too long. Max {max_length} characters allowed, you entered {len(processed_text)}."
        )
    return processed_text 