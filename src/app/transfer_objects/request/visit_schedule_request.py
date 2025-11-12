from dataclasses import dataclass
from typing import Optional


@dataclass
class VisitScheduleRequest:
    """DTO for visit schedule creation.

    Fields:
      - child_record_id: int
      - schedule_date: str (YYYY-MM-DD)
      - schedule_time: str (HH:MM[:SS])
      - visit_purpose: str
      - visit_purpose_other: Optional[str]
      - visit_notes: Optional[str]
    """
    child_record_id: int
    schedule_date: str
    schedule_time: str
    visit_purpose: str
    visit_purpose_other: Optional[str] = None
    visit_notes: Optional[str] = None
