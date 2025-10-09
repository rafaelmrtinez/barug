from datetime import date
import json


from pydantic import BaseModel, field_validator

class MaternalChildRecordEntryResponse(BaseModel):
    visit_id: int | None
    feeding_type_name: str | None
    referred_newborn_screening_date: date | None
    breastfeeding_check_dates: list[date] | None
    is_protected_at_birth: bool | None
    date_assessed: date | None
    date_started: date | None
    date_completed: date | None
    vitamins_given: list[dict] | None
    monitoring_logs: list[dict] | None
    immunizations: list[dict] | None
    latest_tt_vaccine: str | None
    
    @field_validator('vitamins_given', 'monitoring_logs', 'immunizations', mode='before')
    def parse_json(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v