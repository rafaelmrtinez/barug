from dataclasses import dataclass
from typing import Optional


@dataclass
class OperatingDay:
    operating_day_id: Optional[int] = None
    operating_day_start: Optional[int] = None
    operating_day_end: Optional[int] = None
