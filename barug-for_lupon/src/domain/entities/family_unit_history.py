from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FamilyUnitHistory:
    family_history_id: Optional[int] = None
    family_num: Optional[str] = None
    ufc_num: Optional[str] = None
    source_of_income: Optional[str] = None
    hhold_mnthly_income: Optional[float] = None
    created_date: Optional[datetime] = None
    is_active: Optional[bool] = True
    nhts_status_id: Optional[int] = None
    indigent_status_id: Optional[int] = None
    household_type_id: Optional[int] = None
    household_id: Optional[int] = None
    hhold_head_id: Optional[int] = None
    registration_method_id: Optional[int] = None
    added_by_id: Optional[int] = None
    quarter_id: Optional[int] = None
    family_id: Optional[int] = None
