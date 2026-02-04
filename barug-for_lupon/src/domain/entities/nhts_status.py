from dataclasses import dataclass
from typing import Optional


@dataclass
class NHTSStatus:
    nhts_status_id: Optional[int]
    nhts_status_name: str
