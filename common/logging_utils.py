from django.db import connection
from datetime import datetime
from typing import Optional, Any

def log_action(
    record_affected_id: Optional[int],
    table_affected: str,
    action: str,
    performer_id: int,
    user_type_id: int,
    subsystem: str,
    details: Optional[str] = None,
    field_changed: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None
):
    """
    Insert a record into common_log table
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO public.common_log 
            (record_affected_id, details, date_time, table_affected, action, 
             field_changed, old_value, new_value, performer_id, user_type_id, subsystem)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            record_affected_id,
            details,
            datetime.now(),
            table_affected,
            action,
            field_changed,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            performer_id,
            user_type_id,
            subsystem
        ])

def log_business_action(business_id: int, table_affected: str, action: str, performer_id: int, details: str = None):
    """Convenience function for business-related logging"""
    log_action(
        record_affected_id=business_id,
        table_affected=table_affected,
        action=action,
        performer_id=performer_id,
        user_type_id=3,
        subsystem=3,
        details=details,
    )