from django.test import TestCase


from src.infra.adapter.supabase_adapter import SupabaseAdapter

from supabase_client import supabase

class HouseholdRepositoryTestCase(TestCase):
    
    """This is an integration testing for HouseholdRepository class"""
    
    def setUp(self):
        
        self.repo = HouseholdRepository(
            client=SupabaseAdapter(client=supabase)
        )
        
    def test_find_household_by_household_head(self):
        print(self.repo.find_household_by_household_head('x'))
        
    def test_find_household_by_household_number(self):
        result = self.repo.find_household_by_household_number(' '.strip())
        