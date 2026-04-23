from dataclasses import dataclass
from typing import Optional


@dataclass
class Relationship:
    relationship_id: Optional[int]
    relationship_name: str
