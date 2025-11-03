from dataclasses import dataclass
from typing import Optional


@dataclass
class Role:
    role_id: Optional[int]
    role_name: str
