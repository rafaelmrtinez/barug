from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CommonLog:
    common_log_id: Optional[int] = None
    record_affected_id: Optional[int] = None
    details: Optional[str] = None
    date_time: Optional[datetime] = None
    table_affected: Optional[str] = None
    action: Optional[str] = None
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performer_id: Optional[int] = None
    user_type_id: Optional[int] = None
    subsystem: Optional[int] = None
