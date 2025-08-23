from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyCreationPersistence:
    requester_id: str
    household_id: str
    family_number: str
    ucf_number: int
    source_of_income: str
    family_monthly_income: int
    nhts_status: int
    indigent_status: int
    house_type: str
    household_head_relationship: str