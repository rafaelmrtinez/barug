from dataclasses import dataclass
from typing import Optional


@dataclass
class BusinessType:
    business_type_id: Optional[int] = None
    business_type_name: Optional[str] = None
