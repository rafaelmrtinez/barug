from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CreateHouseholdRequest:
    resident_id: str
    house_number: str
    street: str
    sitio: str
    barangay: str
    city: str
    house_type: int
    house_ownership: int
    message: Optional[str] = None