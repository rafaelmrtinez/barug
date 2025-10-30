from dataclasses import dataclass
from typing import Optional

from src.domain.entities.staff import Staff
from src.domain.entities.person import Person


@dataclass
class StaffAggregate:
    staff: Optional[Staff] = None
    person: Optional[Person] = None
