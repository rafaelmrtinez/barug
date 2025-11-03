from dataclasses import dataclass
from typing import Optional


@dataclass
class EmploymentStatusEntity:
    employment_status_id: Optional[int]
    employment_status_name: str
