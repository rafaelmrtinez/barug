from dataclasses import dataclass
from typing import Optional, Any

@dataclass(frozen=True)
class HouseholdListDTO:
    household_id: int
    household_num: str
    household_head: str
    household_address: str
    house_type_name: str
    household_ownership_name: str