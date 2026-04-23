from dataclasses import dataclass
from typing import Optional
from src.domain.entities.person import Person
from src.domain.entities.address import Address


@dataclass
class Household:
    household_id: Optional[int]
    household_num: str
    house_number: str
    household_head: Optional[Person]
    address: Optional[Address]
    is_active: bool = True
    created_date: Optional[str] = None

    def head_name(self) -> Optional[str]:
        return self.household_head.full_name() if self.household_head else None
