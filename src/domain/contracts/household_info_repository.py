from abc import ABC, abstractmethod
from typing import Any


class IHouseholdInfoRepository(ABC):

    @abstractmethod
    def get_family_members_by_family_id(self, family_id) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def get_basic_family_unit_details_by_household_id(self, household_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def get_basic_info_by_id(self, id: int) -> Any:
        raise NotImplementedError()
