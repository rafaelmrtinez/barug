from django.test import TestCase


from src.core.value_objects.family_membership import FamilyMembership


class FamilyMembershipVOTestCase(TestCase):
    
    def setUp(self):
        
        self.test_data = {
            "resident_id": 1,
            "household_id": 1,
            "family_id": 1,
            "is_household_active": True,
            "is_family_active": True,
            "membership_count": 1,
            "residential_status": 5,
            "person_status": 1,
            "residency_period": 1
        }
        
        self.obj = FamilyMembership(**self.test_data)
        
    def test_person_status(self):
        self.obj._FamilyMembership__person_status_validity()
        
    def test_residential_status(self):
        self.obj._FamilyMembership__resident_status_validity()
