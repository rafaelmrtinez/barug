from dataclasses import dataclass


@dataclass(frozen=True)
class HouseholdInformationDTO:
    household_id: str
    house_type_id: int