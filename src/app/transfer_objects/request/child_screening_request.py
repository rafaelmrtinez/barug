from dataclasses import dataclass
from datetime import date

@dataclass
class ChildScreeningRequest:
    is_protected_at_birth: bool | None = None
    date_assessed: date | None = None
    anemic_seen: bool | None = None
    anemic_given_iron: bool | None = None
    birth_weight: float | None = None
    is_low_birth_weight: bool | None = None
    iron_seen_2_6_mos: bool | None = None
    iron_given_2_6_mos: bool | None = None