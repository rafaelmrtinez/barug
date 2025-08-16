import uuid


from django.test import TestCase
from unittest.mock import Mock, patch


from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository
from src.app.services.family_membership import FamilyMembershipService


class FamilyMembershipServiceTestCase(TestCase):

    def setUp(self):
        self.repo: FamilyMembershipRepository = Mock(spec=FamilyMembershipRepository)
        self.service: FamilyMembershipService = FamilyMembershipService(repository=self.repo)
        
        # self.service._FamilyMembershipService__retrieve_resident_data.return_value = {
        #     "resident_id": 'fake-data',
        #     "household_id": 'fake-data',
        #     "family_id": 'fake-data',
        #     "is_household_active": 'fake-data',
        #     "is_family_active": 'fake-data',
        #     "membership_count": 'fake-data'
        # }
        
    @patch.object(FamilyMembershipService, '_FamilyMembershipService__retrieve_resident_data', return_value={
            "resident_id": 'fake-data',
            "household_id": 'fake-data',
            "family_id": 'fake-data',
            "is_household_active": 'fake-data',
            "is_family_active": 'fake-data',
            "membership_count": 'fake-data'
        })
    def test_invalid_exec_data_types_params(self):
        with self.assertRaises(TypeError):
            self.service.execute(
                resident_id='fake-data',  # Invalid type
                household_id='fake-data',
                family_id='fake-data',
                household_head_relationship='fake-data',
                family_head_relationship='fake-data',
                residency_period='fake-data'  # Invalid type
            )
        self.service._FamilyMembershipService__retrieve_resident_data.assert_not_called()