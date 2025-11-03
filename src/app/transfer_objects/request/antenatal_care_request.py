from datetime import date
import json
from typing import Any
from pydantic import BaseModel, field_validator

from src.app.transfer_objects.request.anc_labolatory_results_request import ANCLaboratoryResultsRequest

class AntenatalCareRequest(BaseModel):
    p_maternal_record_id: int | None = None
    p_assessed_by_id: int | None = None
    p_visit_date: date | None = None
    p_trimester_stage_id: int | None = None
    p_prev_illness: str | None = None
    p_prev_hospitalization: str | None = None
    p_prev_preg_complication: str | None = None
    p_num_children_born_alive: int | None = None
    p_num_children_living: int | None = None
    p_num_abortion: int | None = None
    p_num_stillbirth: int | None = None
    p_num_large_babies: int | None = None
    p_has_diabetes: bool | None = None
    p_prev_pregs: list[dict] | None = None
    p_weight: float | None = None
    p_height: float | None = None
    p_bmi_status_id: int | None = None
    p_newborn_plan: bool | None = None
    p_delivery_plan: str | None = None
    p_gravida: int | None = None
    p_para: int | None = None
    p_is_fullterm: bool | None = None
    p_is_preterm: bool | None = None
    p_lmp: date | None = None
    p_edc: date | None = None
    p_lab_results: list[dict] | list[ANCLaboratoryResultsRequest] | None = None
    p_checklist_item_ids: list[int] | None = None
    p_risk_category_ids: list[int] | None = None
    p_tt_vaccines: list[dict] | None = None
    p_iron_start_date: date | None = None
    p_iron_end_date: date | None = None
    p_deworming_date: date | None = None
    
    @field_validator("p_prev_pregs", "p_lab_results", "p_checklist_item_ids", "p_tt_vaccines", mode="before")
    @classmethod
    def parse_json_fields(cls, v: Any):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v