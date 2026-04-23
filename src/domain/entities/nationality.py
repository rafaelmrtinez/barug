from dataclasses import dataclass
from typing import Optional


@dataclass
class Nationality:
    nationality_id: Optional[int]
    nationality_name: str
