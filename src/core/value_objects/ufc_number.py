from dataclasses import dataclass

from src.core.utils.household_number_generator import IdentificationGenerator


@dataclass(frozen=True)
class UFCNumber:
    value: str

    @staticmethod
    def create(house_number: int, family_count: int, exists: callable):
        retries = 0
        while retries < 5:
            candidate = IdentificationGenerator.generate_ucf_number(
                house_number, family_count + retries
            )
            if not exists(candidate):
                return UFCNumber(candidate)
            retries += 1
        raise RuntimeError("Could not generate unique UFC Number")
