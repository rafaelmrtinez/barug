from dataclasses import dataclass
from typing import Optional


@dataclass
class Quarter:
    quarter_id: Optional[int]
    quarter_name: str
