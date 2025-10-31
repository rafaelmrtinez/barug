from dataclasses import dataclass
from typing import Optional


@dataclass
class PersonStatus:
    person_status_id: Optional[int]
    person_status_name: str
