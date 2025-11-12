from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class HouseholdHistory:
    household_id: Optional[int] = None
    household_num: Optional[str] = None
    house_number: Optional[str] = None
    created_date: Optional[datetime] = None
    is_active: Optional[bool] = True
    householdhead_id: Optional[int] = None
    house_type_id: Optional[int] = None
    house_ownership_id: Optional[int] = None
    address_id: Optional[int] = None
    registration_method_id: Optional[int] = None
    household_id_ref: Optional[int] = None
    quarter_id: Optional[int] = None
    added_by_id: Optional[int] = None
