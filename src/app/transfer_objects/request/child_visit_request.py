from dataclasses import dataclass

from src.app.transfer_objects.request.breast_feeding_type_request import BreastFeedingCheckRequest
from src.app.transfer_objects.request.child_immunization_request import ChildImmunizationRequest
from src.app.transfer_objects.request.child_iron_supplement_request import ChildIronSupplementRequest
from src.app.transfer_objects.request.child_monitoring_request import ChildMonitoringRequest
from src.app.transfer_objects.request.child_screening_request import ChildScreeningRequest
from src.app.transfer_objects.request.child_vitamins_request import ChildVitaminsRequest


@dataclass
class ChildVisitRequest:
    p_child_id: int | None = None
    p_child_record_id: int | None = None
    p_assessed_by_id: int | None = None
    p_visit_date: str | None = None
    p_feeding_type_id: int | None = None
    p_referred_nbs_date: str | None = None
    p_child_immunizations: list[ChildImmunizationRequest] | None = None
    p_bf_checks: list[BreastFeedingCheckRequest] | None = None
    p_monitoring_logs: list[ChildMonitoringRequest] | None = None
    p_screening: ChildScreeningRequest | None = None
    p_iron_supplements: ChildIronSupplementRequest | None = None
    p_vitamin_a: list[ChildVitaminsRequest] | None = None
    