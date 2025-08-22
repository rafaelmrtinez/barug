import uuid
from django.test import TestCase

from src.core.aggregates.household import Household
from src.core.entities.household_head import HouseholdHead
from src.core.enums.house_type import HouseType
from src.core.value_objects.home_address import HomeAddress
from src.core.value_objects.household_number import HouseholdNumber


class HouseholdDomainTestCase(TestCase):
    
    def setUp(self):
        self.house_num = HouseholdNumber(
            household_number='4319',
            is_unique=True
        )
        self.addr = HomeAddress(
            house_number="123",
            street="Legazpi Street",
            sitio="colon",
            barangay="señor santo niño",
            city="cebu city"
        )
        self.head = HouseholdHead(
            id=str(uuid.uuid4()),
            name="john doe"
        )
        self.agg = Household(
            id=None,
            household_number=self.house_num,
            address=self.addr,
            head=self.head,
            type='concrete',
            ownership='owned'
        )