from dataclasses import dataclass
from typing import Optional
import uuid

from src.core.entities.household_head import HouseholdHead
from src.core.enums.house_ownership import HouseOwnership
from src.core.enums.house_type import HouseType
from src.core.value_objects.home_address import HomeAddress
from src.core.value_objects.household_number import HouseholdNumber

from src.core.exceptions.domain_exceptions import DomainException

@dataclass
class Household:
    id: uuid.UUID
    household_number: HouseholdNumber
    address: HomeAddress
    type: HouseType
    ownership: HouseOwnership
    head: Optional[HouseholdHead] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4()
            
        if self.type not in HouseType.list_house_types():
            raise DomainException(f"Invalid house type: {self.type}")

        if self.ownership not in HouseOwnership.list_house_ownership_types():
            raise DomainException(f"Invalid house ownership: {self.ownership}")

    def assign_head(self, head: HouseholdHead):
        if self.head is not None:
            raise DomainException("Household already has a head assigned.")
        self.head = head