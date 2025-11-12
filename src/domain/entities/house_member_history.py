from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class HouseMemberHistory:
    house_member_id: Optional[int] = None
    house_member_num: Optional[str] = None
    date_joined: Optional[datetime] = None
    is_active: Optional[bool] = True
    family_id: Optional[int] = None
    relationship_to_hhold_head_id: Optional[int] = None
    relationship_to_fam_head_id: Optional[int] = None
    household_id: Optional[int] = None
    person_id: Optional[int] = None
    added_by_id: Optional[int] = None
    joined_method_id: Optional[int] = None
    quarter_id: Optional[int] = None
    house_member_id_ref: Optional[int] = None
