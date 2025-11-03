from dataclasses import dataclass
from datetime import date

@dataclass
class ImmunizationRequestVersion2:
    p_child_record_id: int
    p_assessed_by_id: int
    p_immunization_type_id: int
    p_immunization_stage_given_id: int
    p_date_given: date