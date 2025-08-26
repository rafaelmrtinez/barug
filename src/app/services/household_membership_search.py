from typing import Any
from src.app.contracts.service import IService
from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository


class HouseholdSearchService(IService):

    def __init__(self, repository: IHouseholdSearchRepository):
        self.repository = repository

    def execute(self, **kwargs) -> Any:
        """Executes the search for household membership based on the provided criteria."""
        key: str = kwargs.get('key', None)
        if not key:
            return None
        return self.repository.find(key)