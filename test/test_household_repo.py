from django.test import TestCase


from src.infra.adapter.supabase_adapter import SupabaseAdapter

from src.infra.repository.household_repository import HouseholdSearchRepository
from supabase_client import supabase

class HouseholdRepositoryTestCase(TestCase):
    
    """This is an integration testing for HouseholdRepository class"""
    
    def setUp(self):
        
        self.repo = HouseholdSearchRepository(
            client=SupabaseAdapter(client=supabase)
        )
        
    def test_find_household_by_household_head(self):
        print(self.repo.find("<>"))
        