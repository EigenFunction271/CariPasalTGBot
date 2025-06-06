# airtable_client.py
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from pyairtable import Table
from pyairtable.formulas import match, OR, GTE, LTE, AND, EQ, FIND, LOWER, NOT
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_PROJECTS_TABLE_NAME = os.getenv('AIRTABLE_PROJECTS_TABLE_NAME')
AIRTABLE_UPDATES_TABLE_NAME = os.getenv('AIRTABLE_UPDATES_TABLE_NAME')
AIRTABLE_TEAMMATE_REQUESTS_TABLE_NAME = os.getenv('AIRTABLE_TEAMMATE_REQUESTS_TABLE_NAME', 'Teammate Requests')

if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PROJECTS_TABLE_NAME, AIRTABLE_UPDATES_TABLE_NAME]):
    raise ValueError("Airtable configuration missing in environment variables.")

projects_table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PROJECTS_TABLE_NAME)
updates_table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_UPDATES_TABLE_NAME)

try:
    teammate_requests_table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TEAMMATE_REQUESTS_TABLE_NAME)
except Exception as e:
    teammate_requests_table = None
    logger.warning(f"Teammate Requests table not found or not configured: {e}")

# --- Projects Logic ---
def add_project(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Adds a new project to the Projects table.
    
    Args:
        project_data: Dict containing project fields matching Airtable columns.
            Required fields: Project Name, Owner Telegram ID, One-liner, Problem Statement,
            Stack, Status, Help Needed
            Optional fields: GitHub/Demo
    
    Returns:
        Created record dict if successful, None if failed
    """
    try:
        # Ensure required fields are present
        required_fields = [
            "Project Name", "Owner Telegram ID", "One-liner", "Problem Statement",
            "Stack", "Status", "Help Needed"
        ]
        for field in required_fields:
            if field not in project_data:
                project_data.setdefault(field, "")

        # Format date in YYYY-MM-DD format for Airtable
        project_data["Last Updated"] = datetime.utcnow().strftime("%Y-%m-%d")
        created_record = projects_table.create(project_data)
        return created_record
    except Exception as e:
        logger.error(f"Error adding project to Airtable: {e}", exc_info=True)
        return None

def get_projects_by_user(telegram_user_id: str) -> List[Dict[str, Any]]:
    """
    Fetches projects owned by a specific Telegram user.
    
    Args:
        telegram_user_id: The Telegram user ID to search for
    
    Returns:
        List of project records
    """
    try:
        formula = match({"Owner Telegram ID": str(telegram_user_id)})
        records = projects_table.all(formula=formula)
        return records
    except Exception as e:
        logger.error(f"Error fetching projects for user {telegram_user_id}: {e}", exc_info=True)
        return []

def add_update(update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Adds a new update to the Updates table and updates the project's Last Updated field.
    
    Args:
        update_data: Dict containing update fields:
            - Project: List of project record IDs
            - Update Text: The update content
            - Blockers: Any blockers mentioned
            - Updated By: Telegram ID of updater
    
    Returns:
        Created update record if successful, None if failed
    """
    try:
        update_data["Timestamp"] = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Ensure required fields are present
        required_fields = ["Project", "Update Text", "Blockers", "Updated By"]
        for field in required_fields:
            if field not in update_data:
                update_data.setdefault(field, "")

        created_update_record = updates_table.create(update_data)

        # Update 'Last Updated' in the Projects table
        if created_update_record and 'Project' in update_data and update_data['Project']:
            project_record_id = update_data['Project'][0]
            projects_table.update(project_record_id, {"Last Updated": update_data["Timestamp"]})
        
        return created_update_record
    except Exception as e:
        logger.error(f"Error adding update to Airtable: {e}", exc_info=True)
        return None

def get_project_details(project_record_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches details for a specific project by its Airtable Record ID.
    
    Args:
        project_record_id: The Airtable record ID of the project
    
    Returns:
        Project record if found, None if not found or error
    """
    try:
        record = projects_table.get(project_record_id)
        return record
    except Exception as e:
        logger.error(f"Error fetching project details for {project_record_id}: {e}", exc_info=True)
        return None
    
def get_projects_created_since(date_since: datetime) -> List[Dict[str, Any]]:
    """
    Fetches projects created on or after a given date.
    
    Args:
        date_since: The datetime to search from
    
    Returns:
        List of project records
    """
    try:
        formula = GTE("Last Updated", date_since)
        records = projects_table.all(formula=formula, sort=["-Last Updated"])
        return records
    except Exception as e:
        logger.error(f"Error fetching projects created since {date_since}: {e}", exc_info=True)
        return []

def get_updates_since(date_since: datetime) -> List[Dict[str, Any]]:
    """
    Fetches updates from the Updates table created on or after a given date.
    
    Args:
        date_since: The datetime to search from
    
    Returns:
        List of update records
    """
    try:
        formula = GTE("Timestamp", date_since)
        records = updates_table.all(formula=formula, sort=["Project (Linked)", "-Timestamp"])
        return records
    except Exception as e:
        logger.error(f"Error fetching updates since {date_since}: {e}", exc_info=True)
        return []

def get_project_name_from_id(project_record_id: str) -> str:
    """
    Helper to get project name from its record ID.
    
    Args:
        project_record_id: The Airtable record ID of the project
    
    Returns:
        Project name or "Unknown Project" if not found
    """
    project_details = get_project_details(project_record_id)
    if project_details and 'fields' in project_details and 'Project Name' in project_details['fields']:
        return project_details['fields']['Project Name']
    return "Unknown Project"

def search_projects(criteria: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Searches projects based on given criteria.
    
    Args:
        criteria: Dict containing search parameters:
            - keyword: Search in name, tagline, problem statement
            - stack: Filter by tech stack
            - status: Filter by project status
    
    Returns:
        List of matching project records
    """
    try:
        formulas = []
        
        keyword = criteria.get("keyword")
        if keyword and keyword.strip():
            keyword_lower = keyword.strip().lower()
            keyword_formula = OR(
                FIND(keyword_lower, LOWER("Project Name")),
                FIND(keyword_lower, LOWER("One-liner")),
                FIND(keyword_lower, LOWER("Problem Statement"))
            )
            formulas.append(keyword_formula)

        stack = criteria.get("stack")
        if stack and stack.strip():
            stack_formula = FIND(stack.strip().lower(), LOWER("Stack"))
            formulas.append(stack_formula)
            
        status = criteria.get("status")
        if status and status.strip():
            status_formula = EQ("Status", status.strip())
            formulas.append(status_formula)

        if not formulas:
            return [] 

        final_formula = AND(*formulas) if len(formulas) > 1 else formulas[0]
        
        records = projects_table.all(formula=final_formula, sort=["-Last Updated"])
        return records
    except Exception as e:
        logger.error(f"Error searching projects with criteria {criteria}: {e}", exc_info=True)
        return []

# --- Teammates Logic ---
def add_teammate_to_project(project_id: str, telegram_id: str) -> bool:
    """
    Adds a Telegram user ID to the Teammates field of a project.
    """
    try:
        project = get_project_details(project_id)
        if not project:
            return False
        teammates = project['fields'].get('Teammates', [])
        if isinstance(teammates, str):
            teammates = [t.strip() for t in teammates.split(',') if t.strip()]
        if telegram_id not in teammates:
            teammates.append(telegram_id)
        projects_table.update(project_id, {"Teammates": ', '.join(teammates)})
        return True
    except Exception as e:
        logger.error(f"Error adding teammate: {e}", exc_info=True)
        return False

def remove_teammate_from_project(project_id: str, telegram_id: str) -> bool:
    """
    Removes a Telegram user ID from the Teammates field of a project.
    """
    try:
        project = get_project_details(project_id)
        if not project:
            return False
        teammates = project['fields'].get('Teammates', [])
        if isinstance(teammates, str):
            teammates = [t.strip() for t in teammates.split(',') if t.strip()]
        teammates = [t for t in teammates if t != telegram_id]
        projects_table.update(project_id, {"Teammates": ', '.join(teammates)})
        return True
    except Exception as e:
        logger.error(f"Error removing teammate: {e}", exc_info=True)
        return False

# --- Teammate Requests Logic ---
def create_teammate_request(project_id: str, requester_id: str) -> bool:
    """
    Creates a teammate join request for a project.
    """
    if not teammate_requests_table:
        logger.warning("Teammate Requests table not configured.")
        return False
    try:
        teammate_requests_table.create({
            "Project": [project_id],
            "Requester Telegram ID": requester_id,
            "Status": "Pending",
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%d")
        })
        return True
    except Exception as e:
        logger.error(f"Error creating teammate request: {e}", exc_info=True)
        return False

def get_pending_requests_for_owner(owner_telegram_id: str) -> list:
    """
    Returns all pending teammate requests for projects owned by the given Telegram ID.
    """
    if not teammate_requests_table:
        return []
    try:
        # Get all projects owned by this user
        projects = get_projects_by_user(owner_telegram_id)
        project_ids = [p['id'] for p in projects]
        if not project_ids:
            return []
        # Find requests for these projects with Status == Pending
        formula = AND(
            OR(*[{{'Project': [pid]}} for pid in project_ids]),
            EQ('Status', 'Pending')
        )
        return teammate_requests_table.all(formula=formula)
    except Exception as e:
        logger.error(f"Error fetching pending teammate requests: {e}", exc_info=True)
        return []

def update_teammate_request_status(request_id: str, status: str) -> bool:
    """
    Updates the status of a teammate request (Approved/Rejected).
    """
    if not teammate_requests_table:
        return False
    try:
        teammate_requests_table.update(request_id, {"Status": status})
        return True
    except Exception as e:
        logger.error(f"Error updating teammate request status: {e}", exc_info=True)
        return False