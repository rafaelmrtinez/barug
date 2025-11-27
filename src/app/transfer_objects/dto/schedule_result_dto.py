from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ScheduleResultDTO:
    """Result of scheduling an announcement"""
    announcement_id: int
    new_status: str
    publish_at: Optional[datetime]