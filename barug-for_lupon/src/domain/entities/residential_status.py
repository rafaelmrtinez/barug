from dataclasses import dataclass
from typing import Optional


@dataclass
class ResidentialStatus:
    residential_status_id: Optional[int]
    residential_status_name: str
