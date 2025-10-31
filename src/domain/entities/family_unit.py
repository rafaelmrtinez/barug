from dataclasses import dataclass
from typing import Optional, List
from src.domain.entities.person import Person


@dataclass
class FamilyUnit:
    family_id: Optional[int]
    family_num: str
    ufc_num: Optional[str]
    source_of_income: Optional[str]
    family_head: Optional[Person]
    is_active: bool = True
    members: List[Person] | None = None

    def member_count(self) -> int:
        return len(self.members) if self.members else 0
