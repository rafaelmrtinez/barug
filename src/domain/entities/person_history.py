from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class PersonHistory:
    person_history_id: Optional[int] = None
    supabase_uid: Optional[str] = None
    person_code: Optional[str] = None
    person_img: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    suffix: Optional[str] = None
    birthdate: Optional[date] = None
    age: Optional[int] = None
    date_added: Optional[datetime] = None
    official_reg_date: Optional[datetime] = None
    email: Optional[str] = None
    mobile_num: Optional[str] = None
    occupation: Optional[str] = None
    date_transferred: Optional[datetime] = None
    is_email_verified: Optional[bool] = None
    is_business_owner: Optional[bool] = None
    is_id_valid: Optional[bool] = None
    is_minor: Optional[bool] = None
    is_student: Optional[bool] = None
    mpin_set: Optional[bool] = None
    residency_period: Optional[int] = None
    mnthly_personal_income_id: Optional[int] = None
    person_id: Optional[int] = None
    sex_id: Optional[int] = None
    address_id: Optional[int] = None
    person_status_id: Optional[int] = None
    residential_status_id: Optional[int] = None
    civil_status_id: Optional[int] = None
    nationality_id: Optional[int] = None
    religion_id: Optional[int] = None
    education_id: Optional[int] = None
    employment_status_id: Optional[int] = None
    registration_method_id: Optional[int] = None
    quarter_id: Optional[int] = None
    added_by_id: Optional[int] = None
