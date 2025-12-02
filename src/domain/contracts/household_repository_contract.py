from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from src.app.transfer_objects.dto.household_dto import (
    HouseholdListDTO,
    HouseholdDetailDTO,
)

class IHouseholdRepository(ABC):

    @abstractmethod
    def fetch_household_list(self) -> list[HouseholdListDTO]:
        pass

    @abstractmethod
    def search_household(self, search: str) -> list[HouseholdListDTO]:
        pass

    @abstractmethod
    def sort_house_type(self, house_type: int) -> list[HouseholdListDTO]:
        pass

    @abstractmethod
    def sort_ownership_type(self, ownership_type: int) ->list[HouseholdListDTO]:
        pass

    @abstractmethod
    def fetch_household_pins(
        self,
        *,
        search: Optional[str] = None,
        house_type: Optional[int] = None,
        ownership_type: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        pass

    @abstractmethod
    def fetch_household_detail(self, household_id: int) -> Optional[HouseholdDetailDTO]:
        pass

