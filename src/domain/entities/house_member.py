from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class HouseMember:
    house_member_id: Optional[int] = None
    date_joined: Optional[datetime] = None
    is_active: Optional[bool] = True
    family_id: Optional[int] = None
    relationship_to_hholdhead_id: Optional[int] = None
    relationship_to_family_head_id: Optional[int] = None
    registration_method_id: Optional[int] = None
    person_id: Optional[int] = None
    added_by_id: Optional[int] = None
