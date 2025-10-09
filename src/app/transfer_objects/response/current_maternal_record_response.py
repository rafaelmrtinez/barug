from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class CurrentMaternalRecordResponse:
    person_id: int
    full_name: str
    visit_date: date | None = None
    maternal_record_id: int | None = None
    trimester_stage_name: str | None = None
    weight: float | None = None
    place_of_delivery_plan: str | None = None
    new_born_screening_plan: str | None = None
    height: float | None = None
    bmi_status_name: str | None = None
    lmp: date | None = None
    edc: date | None = None
    danger_signs: str | None = None