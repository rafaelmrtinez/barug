from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleAnnouncementCMD:
    """Command for scheduling an announcement"""
    announcement_id: int
    scheduled_by_id: Optional[int] = None