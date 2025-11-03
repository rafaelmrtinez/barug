from typing import Optional
from src.infra.exceptions.query_exec_exception import QueryExecutionException
from src.app.transfer_objects.dto.household_dto import(
    HouseholdListDTO,
)
from src.app.contracts.household_service_contract import (
    IHouseholdService,
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)

class HouseholdService(IHouseholdService):
    def __init__(
        self,
        household_repository: IHouseholdRepository,
    ):
        self._household_repo = household_repository

    def execute(
        self, 
        search: Optional[str] = None, 
        house_type: Optional[int] = None, 
        ownership_type: Optional[int] = None,
    ) -> list[HouseholdListDTO]:
        if search:
            return self._household_repo.search_household(search)
        if house_type is not None:
            return self._household_repo.sort_house_type(house_type)
        if ownership_type is not None:
            return self._household_repo.sort_ownership_type(ownership_type)
        
        return self._household_repo.fetch_household_list()