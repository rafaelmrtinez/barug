from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class StaffAccountRequest:
    staff_acc_req_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    suffix: Optional[str] = None
    birthdate: Optional[date] = None
    email: Optional[str] = None
    mobile_num: Optional[str] = None
    date_requested: Optional[datetime] = None
    descriptionn: Optional[str] = None
    sex_id: Optional[int] = None
    address_id: Optional[int] = None
    civil_status_id: Optional[int] = None
    nationality_id: Optional[int] = None
    religion_id: Optional[int] = None
    person_id: Optional[int] = None
    role_id: Optional[int] = None
    requested_by_id: Optional[int] = None
