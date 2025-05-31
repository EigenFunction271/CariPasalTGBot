# airtable_client.py
import os
from pyairtable import Table
from pyairtable.formulas import match
from dotenv import load_dotenv
from datetime import datetime
from datetime import datetime, timedelta
from pyairtable.formulas import OR, GTE, LTE, AND, EQ, FIND, LOWER, NOT # Added EQ, NOT for flexibility
#from pyairtable.formulas import OR, GTE, LTE, AND, FIELD, FORMAT_DATETIME_STR
#from pyairtable.formulas import STR_VALUE, FIND, LOWER, OR, AND # Add AND if not already there


load_dotenv()

AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_PROJECTS_TABLE_NAME = os.getenv('AIRTABLE_PROJECTS_TABLE_NAME')
AIRTABLE_UPDATES_TABLE_NAME = os.getenv('AIRTABLE_UPDATES_TABLE_NAME')

if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PROJECTS_TABLE_NAME, AIRTABLE_UPDATES_TABLE_NAME]):
    raise ValueError("Airtable configuration missing in environment variables.")

projects_table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_PROJECTS_TABLE_NAME)
updates_table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_UPDATES_TABLE_NAME)

def add_project(project_data: dict):
    """
    Adds a new project to the Projects table.
    Expects project_data to contain keys matching Airtable fields.
    - Project Name, Owner Telegram ID, One-liner, Problem Statement, 
    - Stack, GitHub/Demo, Status, Help Needed
    """
    try:
        # Ensure required fields are present as per PRD
        required_fields = ["Project Name", "Owner Telegram ID", "One-liner", "Problem Statement", "Stack", "GitHub/Demo", "Status", "Help Needed"]
        for field in required_fields:
            if field not in project_data:
                # Provide a default or raise an error
                project_data.setdefault(field, "") # Example: default to empty string

        project_data["Last Updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        created_record = projects_table.create(project_data)
        return created_record
    except Exception as e:
        print(f"Error adding project to Airtable: {e}")
        return None

def get_projects_by_user(telegram_user_id: str):
    """
    Fetches projects owned by a specific Telegram user.
    Searches by 'Owner Telegram ID'.
    """
    try:
        formula = match({"Owner Telegram ID": str(telegram_user_id)})
        records = projects_table.all(formula=formula)
        return records
    except Exception as e:
        print(f"Error fetching projects for user {telegram_user_id}: {e}")
        return []

def add_update(update_data: dict):
    """
    Adds a new update to the Updates table.
    Expects update_data:
    - Project (Linked) (Airtable Record ID of the project)
    - Update Text
    - Blockers
    - Updated By (Telegram ID)
    Also updates 'Last Updated' in the linked Project record.
    """
    try:
        update_data["Timestamp"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") #
        
        # Ensure required fields are present
        required_fields = ["Project (Linked)", "Update Text", "Blockers", "Updated By"]
        for field in required_fields:
            if field not in update_data:
                 update_data.setdefault(field, "") # Example: default to empty string

        created_update_record = updates_table.create(update_data)

        # Update 'Last Updated' in the Projects table
        if created_update_record and 'Project (Linked)' in update_data and update_data['Project (Linked)']:
            project_record_id = update_data['Project (Linked)'][0] # Assuming it's a list of one record ID
            projects_table.update(project_record_id, {"Last Updated": update_data["Timestamp"]})
        
        return created_update_record
    except Exception as e:
        print(f"Error adding update to Airtable: {e}")
        return None

def get_project_details(project_record_id: str):
    """
    Fetches details for a specific project by its Airtable Record ID.
    """
    try:
        record = projects_table.get(project_record_id)
        return record
    except Exception as e:
        print(f"Error fetching project details for {project_record_id}: {e}")
        return None
    
def get_projects_created_since(date_since: datetime):
    """
    Fetches projects created on or after a given date.
    (Note: This relies on "Last Updated" as a proxy for creation/recent significant activity)
    """
    try:
        # pyairtable's GTE should handle Python datetime objects correctly.
        formula = GTE("Last Updated", date_since) # Use field name as string
        records = projects_table.all(formula=formula, sort=["-Last Updated"])
        return records
    except Exception as e:
        print(f"Error fetching projects created since {date_since}: {e}")
        return []

def get_updates_since(date_since: datetime):
    """
    Fetches updates from the Updates table created on or after a given date.
    """
    try:
        formula = GTE("Timestamp", date_since) # Use field name as string
        records = updates_table.all(formula=formula, sort=["Project (Linked)", "-Timestamp"])
        return records
    except Exception as e:
        print(f"Error fetching updates since {date_since}: {e}")
        return []

def get_project_name_from_id(project_record_id: str):
    """Helper to get project name from its record ID for the digest."""
    project_details = get_project_details(project_record_id) # Existing function
    if project_details and 'fields' in project_details and 'Project Name' in project_details['fields']:
        return project_details['fields']['Project Name']
    return "Unknown Project"

def search_projects(criteria: dict):
    """
    Searches projects based on given criteria.
    Criteria is a dict: {"keyword": "...", "stack": "...", "status": "..."}
    All criteria are optional. If multiple are provided, they are ANDed.
    """
    try:
        formulas = []
        
        keyword = criteria.get("keyword")
        if keyword and keyword.strip():
            keyword_lower = keyword.strip().lower()
            # Search in Project Name, One-liner, Problem Statement
            # FIND expects the string to search for, then the string to search in (which can be a field or LOWER(field))
            keyword_formula = OR(
                FIND(keyword_lower, LOWER("Project Name")),
                FIND(keyword_lower, LOWER("One-liner")),
                FIND(keyword_lower, LOWER("Problem Statement"))
            )
            formulas.append(keyword_formula)

        stack = criteria.get("stack")
        if stack and stack.strip():
            # Search for substring in the "Stack" field (case-insensitive)
            stack_formula = FIND(stack.strip().lower(), LOWER("Stack"))
            formulas.append(stack_formula)
            
        status = criteria.get("status")
        if status and status.strip():
            # Use EQ for direct equality comparison
            status_formula = EQ("Status", status.strip())
            formulas.append(status_formula)

        if not formulas:
            return [] 

        # Combine all formula parts with AND
        final_formula = AND(*formulas) if len(formulas) > 1 else formulas[0]
        
        records = projects_table.all(formula=final_formula, sort=["-Last Updated"])
        return records
    except Exception as e:
        print(f"Error searching projects with criteria {criteria}: {e}")
        return []


# You can add more utility functions here as needed, e.g., to update specific project fields.