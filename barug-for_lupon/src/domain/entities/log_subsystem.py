from dataclasses import dataclass
from typing import Optional


@dataclass
class LogSubsystem:
    log_subsystem_id: Optional[int]
    log_subsystem_name: str
