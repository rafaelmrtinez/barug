from dataclasses import dataclass
from typing import Optional


@dataclass
class ClearanceStatus:
    clearance_status_id: Optional[int] = None
    clearance_status_name: Optional[str] = None
