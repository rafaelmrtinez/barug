from dataclasses import dataclass
from typing import Optional, List
from datetime import date

@dataclass(frozen=True)
class ResidetDTO:
    person_id: int
    person_code: str
    full_name: str
    address: str
    mob_num: str
    email: str

@dataclass(frozen=True)
class ResidentDetailDTO:
    # Basic Information
    person_id: int
    person_code: str
    first_name: str
    middle_name: Optional[str]
    last_name: str
    suffix: Optional[str]
    birthdate: Optional[date]
    email: Optional[str]
    mobile_num: Optional[str]
    sex: Optional[str]
    age: Optional[int]
    civil_status: Optional[str]
    
    # Address Information
    address_id: Optional[int]
    street_name: Optional[str]
    purok_sitio_name: Optional[str]
    barangay_name: Optional[str]
    city_name: Optional[str]
    
    # Personal Details
    religion: Optional[str]
    nationality: Optional[str]
    education: Optional[str]
    employment_status: Optional[str]
    occupation: Optional[str]
    government_programs: List[str]
    residential_status: Optional[str]
    residency_period: Optional[str]
    resident_since: Optional[str]
    
    # Account Details
    date_added: Optional[date]
    is_email_verified: Optional[bool]
    is_business_owner: Optional[bool]
    is_id_valid: Optional[bool]
    is_student: Optional[bool]
    personal_monthly_income: Optional[str]
    
    # Document Paths
    valid_id_front_path: Optional[str]
    valid_id_back_path: Optional[str]
    id_type_name: Optional[str]
    selfie_with_id: Optional[str]
    profile_picture: Optional[str]
    registration_method: Optional[str]
    
    # Household Information
    household_head_first_name: Optional[str]
    household_head_middle_name: Optional[str]
    household_head_last_name: Optional[str]
    household_head_suffix: Optional[str]
    household_num: Optional[str]
    house_type: Optional[str]
    house_ownership: Optional[str]
    
    # Family Information
    family_head_first_name: Optional[str]
    family_head_middle_name: Optional[str]
    family_head_last_name: Optional[str]
    family_head_suffix: Optional[str]
    family_num: Optional[str]
    household_type: Optional[str]
    nhts_status: Optional[str]
    indigent_status: Optional[str]
    source_of_income: Optional[str]
    family_monthly_income: Optional[str]
    other_family_members: Optional[List[str]]
    
    # Staff Information
    is_staff: Optional[bool]
    staff_id: Optional[int]
    role_name: Optional[str]
    supabase_uid: Optional[str]
    
    # Family Relations
    mother_id: Optional[int]
    mother_name: Optional[str]
    father_id: Optional[int]
    father_name: Optional[str]
    guardian_id: Optional[int]
    guardian_name: Optional[str]
    children_ids: List[int]
    children_names: List[str]