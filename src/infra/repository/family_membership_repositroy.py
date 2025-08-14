from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.core.contracts.infra.family_membership import IFamilyMembershipRepository


class FamilyMembershipRepository(IFamilyMembershipRepository):
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
    
    def get_family_active_status(self, id: str) -> bool:
        """Retrieves the current status of the family"""
        query = (
            self.client
            .table('family_unit')
            .select('is_active')
            .eq('family_id', id)
            .maybe_single()
            .execute()
        )
        return bool(query.data['is_active'])
    
    def find_resident_per_household(self, id: str) -> int:
        """Searched every household if a resident already a member or not"""
        query = (
            self.client
            .table('house_member')
            .select('person_id', count='exact')
            .eq('person_id', id)
            .maybe_single()
            .execute()
        )
        
        if not query:
            return None
        
        return  int(query.data['count'])
        
    def get_household_id(self, id: str) -> str:
        """Fetches the ID of the household"""
        query = (
            self.client
            .table('household_info')
            .select('household_id')
            .eq('household_id', id)
            .maybe_single()
            .execute()
        )
        
        if not query:
            return None
        
        return str(query.data['household_id'])
        
    def join_family_unit(self, data) -> str:
        """Join a resident to a family unit.

        Args:
            data (dict): The data for the family unit.

        Returns:
            str: The ID of the newly created family unit.
        """
        query = (
            self.client.rpc('join_existing_family_unit', params=data)
        )
        if not query:
            return None
        return query.data['v_housemember_req_id']
        
    def get_family_unit_id(self, id: str) -> str:
        """Retrieves the family unit ID for a given resident ID.

        Args:
            id (str): The resident ID.

        Returns:
            str: is_active
        """
        query = (
            self.client
            .table('family_unit')
            .select('family_id')
            .eq('family_id', id)
            .maybe_single()
            .execute()
        )
        if not query:
            return None
        return str(query['family_id'])

    def get_household_active_status(self, id: str) -> bool:
        """
        Retrieves the household ID for a given resident ID.

        :param id: The household  ID.
        :return: The household ID as a string.
        """
        query = (
            self.client
            .table('household_info')
            .select('is_active')
            .eq('household_id', id)
            .maybe_single()
            .execute())
        if not query:
            return False
        return bool(query.data['is_active'])

    def get_resident_id(self, id: str) -> str:
        """
        Retrieves the household ID for a given resident ID.
        
        :param id: The resident ID.
        :return: The household ID as a string.
        """
        query = (
            self.client
            .table('person')
            .select('person_id')
            .eq('person_id', id)
            .maybe_single()
            .execute())
        print(query)
        if not query:
            return None
        return str(query.data['person_id'])