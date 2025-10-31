from dataclasses import dataclass
from typing import Optional


@dataclass
class Religion:
    religion_id: Optional[int]
    religion_name: str
