from dataclasses import dataclass
from typing import Optional


@dataclass
class HouseholdType:
    household_type_id: Optional[int]
    household_type_name: str
