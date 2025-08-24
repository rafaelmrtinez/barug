from django.test import TestCase

from resident.transfer_obj.household_creation_request import CreateHouseholdRequest
from src.app.services.household_creation import HouseholdCreationService
from src.infra.repository.household_creation_repository import HouseholdCreationRepository

from supabase_client import supabase


class HouseholdCreationTestCase(TestCase):
    
    def setUp(self):
        self.service = HouseholdCreationService(
            HouseholdCreationRepository(
                client=supabase
            )
        )
        
        self.request = CreateHouseholdRequest(
            resident_id="304",
            house_number="123",
            message="Requesting household creation",
            house_type="1",
            house_ownership="1",
            city="Quezon City",
            barangay="Barangay 1",
            sitio="Sitio 1",
            street="Street 1"
        )
        
    def test_integration_flow(self):
        rsult = self.service.execute(self.request)
        
        print(rsult)