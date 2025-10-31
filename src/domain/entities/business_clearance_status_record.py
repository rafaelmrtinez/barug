from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class BusinessClearanceStatusRecord:
    brgy_clearance_status_rec_id: Optional[int] = None
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None
    renewed_date: Optional[date] = None
    is_current: Optional[bool] = None
    business_id: Optional[int] = None
    clearance_status_id: Optional[int] = None
