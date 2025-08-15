from unittest import result
from postgrest.exceptions import APIError


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.core.contracts.infra.family_membership import IFamilyMembershipRepository
from src.infra.exceptions.data_access_exception import DataAccessException
from src.infra.exceptions.supabase_sdk.family_member_exist import FamilyMemberAlreadyExistException
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.exceptions.supabase_sdk.missing_response import MissingResponseException
from src.infra.exceptions.supabase_sdk.pending_join_family_request import PendingFamilyRequestException


class FamilyMembershipRepository(IFamilyMembershipRepository):
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
    
    def get_family_active_status(self, id: str) -> bool:
        """Retrieves the current status of the family"""
        try:
            query = (
                self.client
                .table('family_unit')
                .select('is_active')
                .eq('family_id', id)
                .maybe_single()
                .execute()
            )
            if not query:
                raise DataAccessException("Family unit not found.")
            return bool(query.data['is_active'])
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
    
    def find_resident_per_household(self, id: str) -> int:
        """Searched every household if a resident already a member or not"""
        try:
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
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
        
    def get_household_id(self, id: str) -> str:
        """Fetches the ID of the household"""
        try:
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
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
        
    def join_family_unit(self, data) -> str:
        """Join a resident to a family unit.

        Args:
            data (dict): The data for the family unit.

        Returns:
            str: The ID of the newly created family unit.
        """
        try:
            query = (
            self.client
            .rpc('join_existing_family_unit', params=data)
            .execute()
        )
            if not query:
                return None
            return query.data
        except APIError as e:
            if getattr(e, 'code') == '23503' and str(e.message).__contains__('violates foreign key constraint'):
                raise ForeignKeyException(str(e.message).upper())
            if getattr(e, 'code') == 'P5035' and getattr(e, 'message') == 'You already have a pending request to join a household.':
                raise PendingFamilyRequestException(str(e.message).upper())
            if getattr(e, 'code') == '22P02' and getattr(e, 'message') == 'invalid input syntax for type integer: "You are already a member of this family unit."':
                raise FamilyMemberAlreadyExistException(str(e.message).upper())
            raise e
            
        
    def get_family_unit_id(self, id: str) -> str:
        """Retrieves the family unit ID for a given resident ID.

        Args:
            id (str): The resident ID.

        Returns:
            str: is_active
        """
        try:
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
        except APIError as e:
            if getattr(e, 'code') == '204' and getattr(e, 'message') == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")

    def get_household_active_status(self, id: str) -> bool:
        """
        Retrieves the household ID for a given resident ID.

        :param id: The household  ID.
        :return: The household ID as a string.
        """
        try:
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
        except APIError as e:
            if getattr(e, 'code', None) == '204' and getattr(e, 'message') == 'Missing response':
                raise MissingResponseException(e)

    def get_resident_id(self, id: str) -> str:
        """
        Retrieves the household ID for a given resident ID.
        
        :param id: The resident ID.
        :return: The household ID as a string.
        """
        try:
            query = (
            self.client
            .table('person')
            .select('person_id')
            .eq('person_id', id)
            .maybe_single()
            .execute())
            if not query:
                return None
            return str(query.data['person_id'])
        except APIError as e:
            if getattr(e, 'code', None) == '204' and getattr(e, 'message') == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")