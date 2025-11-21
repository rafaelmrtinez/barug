# lupon_mem/utils/logging.py
from django.db import connection
from typing import Optional, Dict, Any
import json

def blotter_log_event(
    action: str,
    table_affected: str,
    record_affected_id: int,
    details: Optional[Dict[str, Any]] = None,
    performer_staff_id: Optional[int] = None,
    performer_person_id: Optional[int] = None,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None
) -> None:
    """
    Log an event using the blotter_log_event database function.
    
    Args:
        action: The action performed (e.g., 'CREATE', 'UPDATE', 'DELETE')
        table_affected: The table that was affected
        record_affected_id: The ID of the affected record
        details: Additional details as a dictionary (will be converted to JSON)
        performer_staff_id: ID of the staff member performing the action
        performer_person_id: ID of the person performing the action
        field_changed: Name of the field that was changed
        old_value: Previous value of the field
        new_value: New value of the field
    """
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT blotter_log_event(
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, [
                action,
                table_affected,
                record_affected_id,
                json.dumps(details) if details else None,
                performer_staff_id,
                performer_person_id,
                field_changed,
                old_value,
                new_value
            ])
    except Exception as e:
        # Log the error but don't fail the main operation
        print(f"Failed to log event: {e}")