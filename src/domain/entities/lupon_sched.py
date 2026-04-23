from dataclasses import dataclass
from datetime import time
from typing import Optional


@dataclass
class LuponSched:
    lupon_sched_id: Optional[int] = None
    day: Optional[int] = None
    time_start: Optional[time] = None
    time_end: Optional[time] = None
