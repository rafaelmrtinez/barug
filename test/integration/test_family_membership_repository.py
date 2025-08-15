from django.test import TestCase


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException
from src.infra.exceptions.supabase_sdk.family_member_exist import FamilyMemberAlreadyExistException
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.exceptions.supabase_sdk.missing_response import MissingResponseException
from src.infra.exceptions.supabase_sdk.pending_join_family_request import PendingFamilyRequestException
from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository


from supabase_client import supabase


class FamilyMembershipRepositoryTestCase(TestCase):
    
    def setUp(self):
        self.repository = FamilyMembershipRepository(
            client=SupabaseAdapter(
                client=supabase
            )
        )
        
    def test_get_resident_full_details_invalid_params(self):
        with self.assertRaises(MissingResponseException) as e:
            self.repository.get_resident_basic_info('a')
        self.assertRaises(MissingResponseException)

    def test_get_family_active_status_invalid_data(self):
        with self.assertRaises(MissingResponseException) as mre:
            self.repository.get_family_active_status('a')
        self.assertRaises(MissingResponseException)        
        
    def test_find_resident_per_household_invalid_data(self):
        with self.assertRaises(MissingResponseException) as mre:
            self.repository.find_resident_per_household('a')
            
        self.assertRaises(MissingResponseException)
        
    def test_get_household_id_invalid_data(self):
        with self.assertRaises(MissingResponseException) as e:
            self.repository.get_household_id('a')
        self.assertRaises(MissingResponseException)
        
    def test_join_existing_family_unit_invalid_data(self):
        with self.assertRaises((
            ForeignKeyException, 
            PendingFamilyRequestException,
            FamilyMemberAlreadyExistException)) as dae:
            self.repository.join_family_unit(
            {
                'p_requester_id': 2290,
                'p_family_id': 100,
                'p_relationship_to_hholdhead_id': 100,
                'p_relationship_to_family_head_id': 100,
                'p_residency_period': -1
            }
        )
        self.assertRaises((
            ForeignKeyException, 
            PendingFamilyRequestException, 
            FamilyMemberAlreadyExistException))
        
    def test_get_family_unit_id_pass_str_or_none(self):
        result = None
        with self.assertRaises(MissingResponseException) as mre:
            self.repository.get_family_unit_id(None)

        self.assertRaises(MissingResponseException)

    def test_get_household_active_status_pass_str_or_none(self):
        result = None
        with self.assertRaises(MissingResponseException) as mre:
            result = self.repository.get_household_active_status('e')
        self.assertIsNone(result)
        self.assertRaises(MissingResponseException)
        
    def test_get_resident_id_pass_str_or_none(self):
        result = None
        with self.assertRaises(MissingResponseException) as mre:
            result = self.repository.get_resident_id('a')
        self.assertIsNone(result)
        self.assertRaises(MissingResponseException)