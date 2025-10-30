from dataclasses import dataclass
from datetime import time
from typing import Optional


@dataclass
class OperatingHour:
    operating_hour_id: Optional[int] = None
    operating_hour_start: Optional[time] = None
    operating_hour_end: Optional[time] = None
