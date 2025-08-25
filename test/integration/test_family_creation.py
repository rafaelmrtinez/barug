from django.test import TestCase

from src.app.services.family_creation import FamilyCreationService
from src.app.transfer_objects.commands.family_creation import FamilyCreationRequest
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.repository.family_creation_repository import FamilyCreationRepository
from src.infra.repository.household_search_repository import HouseholdSearchRepository
from src.infra.repository.resident_repository import ResidentRepository
from supabase_client import supabase


class FamilyCreationServiceTest(TestCase):

    def setUp(self):

        self.service = FamilyCreationService(
            family_creation_repo=FamilyCreationRepository(
                client=SupabaseAdapter(
                    client=supabase
                )
            )
        )

    def test_service_flow(self):
        cmd = FamilyCreationRequest(
            requester_id=321,
            household_number=54321,
            household_head_relationship=3,
            indigent_status=1,
            source_of_income="software engineer",
            family_monthly_income=5,
            nhts_status=1)
        result = self.service.execute(cmd)
        print(result)
