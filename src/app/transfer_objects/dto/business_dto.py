from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any
from datetime import date, time, datetime

@dataclass(frozen=True)
class BusinessListDTO:
    business_id: int
    business_name: str
    business_category_name: str
    business_nature: str
    business_owner_name: str
    business_address: str
    business_status_name: str
    ownership_type_name: str

@dataclass(frozen=True)
class ResidentOwnerDTO:
    person_id: int
    person_code: Optional[str]
    full_name: str

    # Optional extras (default to None so construction never crashes)
    sex_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    address_line: Optional[str] = None

    # Keep the name you’re already using in repo + normalizer
    residential_status_name: Optional[str] = None
    civil_status: Optional[str] = None
    nationality: Optional[str] = None
    religion: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None

    # raw address fields
    street: Optional[str] = None
    purok: Optional[str] = None
    barangay: Optional[str] = None
    city: Optional[str] = None

@dataclass(frozen=True)
class NonResidentOwnerDTO:
    last_name: str
    first_name: str
    middle_name: Optional[str]
    suffix: Optional[str]

    sex_id: int
    sex_name: str

    date_of_birth: date

    civil_status_id: int
    civil_status_name: str

    nationality_id: int
    nationality_name: str

    religion_id: int
    religion_name: str

    email: str
    mobile: str

    address_id: int
    street: str
    purok_sitio_id: int
    purok: str
    barangay: str
    city: str
    latitude: Optional[float]
    longitude: Optional[float]

@dataclass(frozen=True)
class BusinessInfoDTO:
    b_name: str
    ownership_type: int
    b_category: int
    b_nature: str
    date_est: date

    dti: str
    capital_invested: str
    prev_gross: str
    monthly_est: str
    emp_num: int

    street: str
    purok_sitio: str
    barangay: str
    city: str
    latitude: float
    longitude: float
    loc_desc: str

    opt_days_start: int
    opt_days_end: int
    opt_hrs_start: time
    opt_hrs_end: time

    proof_name: str

@dataclass(frozen=True)
class OwnerBusinessDTO:
    owner: dict[str, Any]
    business: dict[str, Any]
    # owner_id: dict[str, Any]
    business_proof: dict[str, Any]

@dataclass(frozen=True)
class RenewalListDTO:
    business_id: int
    business_name: str
    owner_fullname: str
    clearance_state: str
    has_active_renewal_request: bool
    open_renewal_request_count: int
    valid_from: Optional[str]
    expires_on: Optional[str]
    extension: Optional[str]

@dataclass(frozen=True)
class RenewalQuoteLineDTO:
    business_id: int
    item_year: int
    kind: str                        
    is_paid: Optional[bool]         
    paid_on: Optional[datetime]
    or_number: Optional[str]
    base_fee: Decimal
    offense_no: Optional[int]
    surcharge: Decimal
    total: Decimal
    deadline: Optional[date]
    days_late: Optional[int]
