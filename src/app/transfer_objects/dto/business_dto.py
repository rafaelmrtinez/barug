from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class BusinessListDTO:
    business_id: int
    business_name: str
    business_type_name: str
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