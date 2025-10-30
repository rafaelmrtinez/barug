from dataclasses import dataclass
from typing import Optional, List
from src.domain.entities.household import Household
from src.domain.entities.family_unit import FamilyUnit


@dataclass
class HouseholdAggregate:
    household: Household
    families: Optional[List[FamilyUnit]] = None

    def total_family_members(self) -> int:
        if not self.families:
            return 0
        return sum(f.member_count() for f in self.families)
