from dataclasses import dataclass
from typing import Optional


@dataclass
class RegistrationMethod:
    registration_method_id: Optional[int]
    registration_method_name: str
