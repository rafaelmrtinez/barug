from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class PreviousMaternalRecordResponse:
    visit_date: date | None = None
    trimester_stage_name: str | None = None
    weight: float | None = None 
    bmi_status_name: str | None = None
    danger_signs: str | None = None