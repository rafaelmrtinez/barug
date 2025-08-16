from django.test import TestCase


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository


from supabase_client import supabase


class FamilyMembershipRepositoryTestCase(TestCase):
    
    """
        The behaviors being checked by this class should remain commented out (At least for now).
    Unless we need to debug a specific issue that related to INTEGRATION.
    
        Otherwise, if there is no need to perform INTEGRATION TESTING, please leave the below behaviors
    as is.
    """
    
    def setUp(self):
        self.repository = FamilyMembershipRepository(
            client=SupabaseAdapter(
                client=supabase
            )
        )
        
    # def test_get_resident_basic_info(self):
    #     result = self.repository.get_resident_basic_info(228)
    #     self.assertIsInstance(result, dict)
    #     self.assertEqual(type(result['residential_status_id']), int)
    #     self.assertEqual(type(result['person_status_id']), int)
    #     self.assertEqual(type(result['residency_period']), int)

    # def test_get_household_status(self):
    #     result = self.repository.get_household_status(2)
    #     self.assertIsInstance(result, bool)
        
    # def test_get_family_unit_status(self):
    #     result = self.repository.get_family_unit_status(1)
    #     self.assertIsInstance(result, bool)
        
    # def test_find_resident(self):
    #     result = self.repository.find_resident(1)
    #     self.assertIsInstance(result, int)