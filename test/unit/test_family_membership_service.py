import uuid


from django.test import TestCase
from unittest.mock import Mock, patch


from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository
from src.app.services.family_membership import FamilyMembershipService


class FamilyMembershipServiceTestCase(TestCase):

    def setUp(self):
        stub_repo = Mock(spec=FamilyMembershipRepository)
        self.service = FamilyMembershipService(repository=stub_repo)
        
        stub_repo.get_resident_basic_info.return_value = {
            "residential_status_id": 1,
            "person_status_id": 1,
            "residency_period": 12
        }
        stub_repo.find_resident.return_value = 1
        stub_repo.get_household_status.return_value = True
        stub_repo.get_family_unit_status.return_value = True


    def test_data_retrieval(self):
        
        result = self.service._FamilyMembershipService__retrieve_resident_data(1, 1, 1)
        
        expected_data = {
            "resident_id": 1,
            "household_id": 1,
            "family_id": 1,
            "is_household_active": True,
            "is_family_active": True,
            "membership_count": 1,
            "residential_status": 1,
            "person_status": 1,
            "residency_period": 12
        }
        
        self.assertEqual(result, expected_data)

