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
        
    def find_resident(self, id: int) -> int:
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
                return -1
            return  int(query.count)
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
        
    def insert_membership(self, data) -> str:
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
        
    def get_family_unit_status(self, id: int) -> bool:
        try:
            query = (
                self.client
                .table('family_unit')
                .select('is_active')
                .eq('family_id', id)
                .maybe_single()
                .execute()
            )
            return query.data['is_active'] if query.data else None
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
        
    def get_household_status(self, id: int) -> bool:
        try:
            query = (
                self.client
                .table('household_info')
                .select('is_active')
                .eq('household_id', id)
                .maybe_single()
                .execute()
            )
            if not query:
                return None
            return query.data['is_active']
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e
    
    def get_resident_basic_info(self, id: int) -> dict:
        try:
            query = (
                self.client
                .table('person')
                .select('residential_status_id, person_status_id, residency_period')
                .eq('person_id', id)
                .maybe_single()
                .execute()
            )
            if not query:
                return None
            return query.data
        except APIError as e:
            if str(e.code) == '204' and str(e.message) == 'Missing response':
                raise MissingResponseException("Data source returned a 204 No Content — possibly empty dataset.")
            raise e