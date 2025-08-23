from django.test import TestCase

from src.app.services.family_creation import FamilyCreationService
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.repository.family_creation_repository import FamilyCreationRepository
from src.infra.repository.household_search_repository import HouseholdSearchRepository
from src.infra.repository.resident_repository import ResidentRepository
from supabase_client import supabase

class FamilyCreationServiceTest(TestCase):
    
    def setUp(self):

        self.service = FamilyCreationService(
            resident_repo=ResidentRepository(client=SupabaseAdapter(client=supabase)),
            household_repo=HouseholdSearchRepository(client=SupabaseAdapter(client=supabase)),
            family_creation_repo=FamilyCreationRepository(client=SupabaseAdapter(client=supabase))
        )
        
    def test_service_flow(self):
        result = self.service.execute(
            user_id=302,
            household_number=12345,
            household_head_relationship=3,
            indigent_status=1,
            source_of_income="software engineer",
            family_monthly_income=5,
            nhts_status=1
        )
        
        print(result)