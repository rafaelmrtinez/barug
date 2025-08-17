from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository


class HouseholdMembershipHSearchService:

    def __init__(self, repository: IHouseholdSearchRepository):
        self.repository = repository
        
    def execute(self, key: str):
        """
        Searches for household members by household ID.
        
        :param household_id: The ID of the household to search for members.
        :return: A list of household members.
        """
        return self.repository.find(key)