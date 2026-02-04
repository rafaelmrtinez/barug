from dataclasses import dataclass
from typing import Optional


@dataclass
class SchedulingConfig:
    config_id: Optional[int] = None
    total_week_limit: int = 100
    default_bhw_week_limit: int = 50
