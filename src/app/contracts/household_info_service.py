from abc import ABC, abstractmethod
from typing import Any, Dict


class IHouseholdInformationService(ABC):

    @abstractmethod
    def execute(self, household_id: int) -> Dict[str, Any]:
        """Return normalized household information and family units."""
        raise NotImplementedError()
