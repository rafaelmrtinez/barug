from dataclasses import dataclass
from typing import Optional


@dataclass
class HouseOwnership:
    house_ownership_id: Optional[int]
    house_ownership_name: str
