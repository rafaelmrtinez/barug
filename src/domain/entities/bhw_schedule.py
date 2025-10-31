from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Optional


@dataclass
class BhwSchedule:
    schedule_id: Optional[int] = None
    week_id: Optional[int] = None
    reschedule_count: Optional[int] = 0
    remarks: Optional[str] = None
    resched_reason: Optional[str] = None
    is_rescheduled: Optional[bool] = False
    accomplished_date: Optional[datetime] = None
    status: Optional[int] = None
    bhw_id: Optional[int] = None
    household_id: Optional[int] = None
