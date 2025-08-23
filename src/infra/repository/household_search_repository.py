from postgrest.exceptions import APIError


from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException


class HouseholdSearchRepository(IHouseholdSearchRepository):
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
        
    def get_all_family_count(self):
        result = (
            self.client.table('family_unit')
            .select(count='exact')
            .execute()
        )
        
        if not result.data:
            return None
        
        return result.count if result.count else 0
        
    def get_family_count_by_household_id(self, id):
        result = (
            self.client.table('family_unit')
            .select('family_id', count='exact')
            .eq('household_id', id)
            .execute()
        )
        
        if not result.data:
            return None
        
        return result.count if result.count else 0
        
    def get_household_info_by_house_num(self, house_num: str) -> dict:
        result = (
            self.client
            .table('household_info')
            .select('household_id, house_type(house_type_id)')
            .eq('house_number', house_num)
            .execute()
        )
        return result.data[0] if result.data else {}


    def get(self, household_id) -> dict:
        try:
            result = (
                self.client
                .table('family_unit')
                .select('family_id, person(first_name, last_name, middle_name, suffix), family_num, is_active')
                .eq('household_id', household_id)
                .execute()
            )
            
            address = (
                self.client
                .table('household_info')
                .select('addresss(street(street_name, purok_sitio(purok_sitio_code, purok_sitio_name), barangay(barangay_name), city(city_name)))')
                .eq('household_id', household_id)
                .execute()
            )
            
            if not result.data or not address.data:
                return {}

            return {
                "family_data": result.data,
                "address_data": address.data
            }
        except APIError as e:
            raise DataAccessException(str(e)) from e

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