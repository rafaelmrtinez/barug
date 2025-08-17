from postgrest.exceptions import APIError


from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException


class HouseholdSearchRepository(IHouseholdSearchRepository):
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
        
    def find(self, key: str) -> dict:
        """This method will find every household information by household number or head.

        Args:
            key (str): The household number or head to search for.

        Returns:
            dict: The return data will consist of
            - Household Head Full Name (str)
            - Household Number (str)
            - Active Status (boolean)
        """
        try:
            result = self.client.rpc('search_households', {'p_search': key}).execute()
            if not result.data:
                return {}
            return result.data
        except APIError as e:
            raise DataAccessException("Error occurred while searching households") from e