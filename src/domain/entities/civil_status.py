from dataclasses import dataclass
from typing import Optional


@dataclass
class CivilStatus:
    civil_status_id: Optional[int] = None
    civil_status_name: Optional[str] = None
