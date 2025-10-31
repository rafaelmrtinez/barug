from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class CalendarWeek:
    week_id: Optional[int] = None
    week_start: Optional[date] = None
    week_end: Optional[date] = None
    year_num: Optional[int] = None
    week_label: Optional[str] = None
    quarter_id: Optional[int] = None
