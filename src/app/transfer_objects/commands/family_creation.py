from dataclasses import dataclass

@dataclass(frozen=True)
class FamilyCreationCommand:
    nhts_status: int
    requester_id: str
    indigent_status: int
    household_number: str
    source_of_income: str
    family_monthly_income: int
    household_head_relationship: int