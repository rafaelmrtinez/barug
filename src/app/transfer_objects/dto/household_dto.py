from dataclasses import dataclass
from typing import Optional, Any, List

@dataclass(frozen=True)
class HouseholdListDTO:
    household_id: int
    household_num: str
    household_head: str
    household_address: str
    house_type_name: str
    household_ownership_name: str

@dataclass(frozen=True)
class HouseholdMemberDTO:
    person_id: int
    full_name: str
    relationship_to_household_head: Optional[str]
    age: Optional[int]
    sex: Optional[str]

@dataclass(frozen=True)
class FamilyDTO:
    family_id: int
    family_num: str
    family_head_name: str
    household_type: Optional[str]
    nhts_status: Optional[str]
    indigent_status: Optional[str]
    monthly_income: Optional[str]
    source_of_income: Optional[str]
    members: List[HouseholdMemberDTO]

@dataclass(frozen=True)
class HouseholdDetailDTO:
    household_id: int
    household_num: str
    household_head_name: str
    house_type: Optional[str]
    house_ownership: Optional[str]
    address: str
    families: List[FamilyDTO]