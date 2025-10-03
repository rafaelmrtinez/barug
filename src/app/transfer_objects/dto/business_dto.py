from dataclasses import dataclass

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
    person_code: str
    full_name: str
    sex_name: str
    date_of_birth: str
    address_line: str
    residential_status: str
    civil_status: str
    nationality: str
    religion: str
    mobile: str
    email: str