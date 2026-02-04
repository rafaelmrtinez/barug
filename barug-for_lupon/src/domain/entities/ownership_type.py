from dataclasses import dataclass
from typing import Optional


@dataclass
class OwnershipType:
    ownership_type_id: Optional[int] = None
    ownership_type_name: Optional[str] = None
