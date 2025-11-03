from dataclasses import dataclass
from datetime import date

@dataclass
class ChildImmunizationRequest:
    immunization_type_id: int | None = None
    date_given: date | None = None
    immunization_stage_given_id: int | None = None
