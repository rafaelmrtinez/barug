import datetime
from src.core.utils.household_number_generator import IdentificationGenerator


class HouseholdNumber:
    def __init__(self, value: str):
        self.value = value

    @staticmethod
    def create(house_number: int, date: datetime, exists: callable) -> "HouseholdNumber":
        retries = 0
        while retries < 5:
            candidate = IdentificationGenerator.generate_household_number(
                house_number, f"{date.month:02d}", str(date.year)[-2:]
            )
            if not exists(candidate):
                return HouseholdNumber(candidate)
            retries += 1
        raise RuntimeError("Could not generate unique HouseholdNumber")
