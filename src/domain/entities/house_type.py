from dataclasses import dataclass
from typing import Optional


@dataclass
class HouseType:
    house_type_id: Optional[int]
    house_type_name: str
