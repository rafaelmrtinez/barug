from dataclasses import dataclass
from typing import Optional


@dataclass
class BusinessStatus:
    business_status_id: Optional[int] = None
    business_status_name: Optional[str] = None
