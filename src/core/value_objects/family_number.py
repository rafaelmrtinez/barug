import datetime
from dataclasses import dataclass

from src.core.utils.household_number_generator import IdentificationGenerator

@dataclass(frozen=True)
class FamilyNumber:
    value: str
    
    @staticmethod
    def create(house_number: int, family_count: int, exists: callable):
        retries = 0
        while retries < 5:
            candidate = IdentificationGenerator.generate_family_number(
                house_number, family_count
            )
            if not exists(candidate):
                return FamilyNumber(candidate)
            retries += 1
        raise RuntimeError("Could not generate unique HouseholdNumber")
    