from dataclasses import dataclass
from typing import Optional


@dataclass
class IndigentStatus:
    indigent_status_id: Optional[int]
    indigent_status_name: str
