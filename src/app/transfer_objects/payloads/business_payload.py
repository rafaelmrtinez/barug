# src/app/transfer_objects/payloads/owner_payload.py
from typing import TypedDict, Optional

class OwnerPayload(TypedDict, total=False):
    owner_person_id: Optional[int]  # if reusing an existing resident
    last_name: str
    first_name: str
    middle_name: Optional[str]
    suffix: Optional[str]
    birthdate: str  # "YYYY-MM-DD"
    email: Optional[str]
    mobile: Optional[str]
    sex_id: int
    civil_status_id: int
    nationality_id: int
    religion_id: int
    street: str
    purok_sitio_name: Optional[str]  # or use *_id if that’s your form
    barangay: str
    city: str
    valid_id_type_id: Optional[int]
    valid_id_front: Optional[str]
    valid_id_back: Optional[str]
