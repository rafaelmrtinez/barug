from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from src.app.transfer_objects.dto.household_dto import (
    HouseholdListDTO,
)

class IHouseholdService(ABC):

    @abstractmethod
    def execute(
        self,
        search: Optional[str],
        house_type: Optional[int],
        ownership_type: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        pass