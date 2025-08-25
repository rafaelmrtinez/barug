from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyEligibilityContext:
    household_number: int
    household_head_relationship: str
    has_existing_household: bool
    pending_requests: int