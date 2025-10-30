from dataclasses import dataclass
from typing import Optional
from src.domain.entities.person import Person


@dataclass
class Staff:
    staff_id: Optional[int]
    staff_code: str
    person: Person
    assigned_sitio: Optional[str] = None
    weekly_capacity: Optional[int] = None
    role_id: Optional[int] = None
    acc_status_id: Optional[int] = None

    def display_name(self) -> str:
        return self.person.full_name()
