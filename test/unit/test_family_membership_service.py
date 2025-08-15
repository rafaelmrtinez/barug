import uuid


from django.test import TestCase
from unittest.mock import Mock


from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository
from src.app.services.family_membership import FamilyMembershipService


class FamilyMembershipServiceTestCase(TestCase):

    def setUp(self):
        self.repo: FamilyMembershipRepository = Mock(spec=FamilyMembershipRepository)
        self.service: FamilyMembershipService = FamilyMembershipService(repository=self.repo)
        
        self.repo.find_resident_per_household.return_value = 0
        self.repo.get_household_id.return_value = str(uuid.uuid4())
        self.repo.get_resident_id.return_value = str(uuid.uuid4())
        self.repo.join_family_unit.return_value = "Family joined!"
        self.repo.get_family_unit_id.return_value = str(uuid.uuid4())
        self.repo.get_household_active_status.return_value = True
        self.repo.get_family_active_status.return_value = True
        self.repo.join_family_unit.return_value = str(uuid.uuid4())
        
    def __service_template(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.execute(
                resident_id=uuid.uuid4(),
                household_id=uuid.uuid4(),
                family_id=uuid.uuid4(),
                household_head_relationship=1,
                family_head_relationship=1,
                residency_period=5
            )
        return ctx
    
    def test_resident_already_exist_in_family(self):
        pass
    
    def test_join_family_unit_none_returned(self):
        self.repo.join_family_unit.return_value = None
        ctx = self.__service_template()
        self.assertIn("Unable to join family at the moment.", str(ctx.exception))
    
    def test_is_family_active(self):
        self.repo.get_family_active_status.return_value = False
        ctx = self.__service_template()
        self.assertIn('Family unit is no longer active.', str(ctx.exception))

    def test_is_household_active(self):
        self.repo.get_household_active_status.return_value = False
        ctx = self.__service_template()
        self.assertIn("Household is no longer active.", str(ctx.exception))

    def test_is_resident_exist_at_other_family(self):
        self.repo.find_resident_per_household.return_value = 1
        ctx = self.__service_template()
        self.assertIn("Unable to proceed request, dual membership found.", str(ctx.exception))

    def test_family_id_not_exist(self):
        self.repo.get_family_unit_id.return_value = None
        ctx = self.__service_template()
        self.assertIn("Family does not exist.", str(ctx.exception))

    def test_household_not_exist(self):
        self.repo.get_household_id.return_value = None
        ctx = self.__service_template()
        self.assertIn("Household does not exist.", str(ctx.exception))

    def test_resident_not_found_empty_str(self):
        self.repo.get_resident_id.return_value = ""
        ctx = self.__service_template()
        self.assertIn("Resident does not exist", str(ctx.exception))

    def test_resident_not_found(self):
        self.repo.get_resident_id.return_value = None
        ctx = self.__service_template()
        self.assertIn("Resident does not exist", str(ctx.exception))

    def test_service_execution(self):
        result = self.service.execute(
                resident_id=uuid.uuid4(),
                household_id=uuid.uuid4(),
                family_id=uuid.uuid4(),
                household_head_relationship=1,
                family_head_relationship=1,
                residency_period=5
            )
        self.assertIsNotNone(result, "Result is none!")
        self.assertEqual(result, "OK")
