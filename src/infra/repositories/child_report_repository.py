from typing import Any, Dict, List, Optional

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

import logging

logger = logging.getLogger(__name__)


class ChildReportRepository:
    """Repository for assembling data required by child health summary reports.

    Methods return plain python dicts/lists so the service can format them
    into a PDF document.
    """

    def __init__(self, ctx: ConnectionAdapter):
        self.ctx = ctx

    def fetch_patient_info(self, child_record_id: int) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            c.child_record_id,
            p.person_id,
            p.first_name,
            p.last_name,
            p.middle_name,
            p.birthdate,
            p.age,
            p.mobile_num,
            f.family_num,
            c.birth_order,
            c.created_at,
            d.delivery_place_type_name,
            m.person_id as mother_id,
            m.first_name as mother_first_name,
            m.last_name as mother_last_name,
            fa.person_id as father_id,
            fa.first_name as father_first_name,
            fa.last_name as father_last_name
        FROM public.child_health_record c
        LEFT JOIN public.person p ON p.person_id = c.person_id
        LEFT JOIN public.family_unit f ON f.family_id = c.family_id
        LEFT JOIN public.delivery_place_type d ON d.delivery_place_type_id = c.delivery_place_type_id
        LEFT JOIN public.person m ON m.person_id = c.mother_id
        LEFT JOIN public.person fa ON fa.person_id = c.father_id
        WHERE c.child_record_id = %s
        LIMIT 1;"""
        try:
            rows = self.ctx.execute_query_to_dict(sql, (child_record_id,))
            return rows[0] if rows else None
        except QueryExecutionException:
            logger.exception("Failed to fetch patient info for child record %s", child_record_id)
            return None

    def fetch_immunizations(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = (
            "SELECT ci.child_immunization_id, ci.date_given, it.immunization_type_name, "
            "isg.immunization_stage_name "
            "FROM public.child_immunization ci "
            "LEFT JOIN public.immunization_type it ON it.immunization_type_id = ci.immunization_type_id "
            "LEFT JOIN public.immunization_stage_given isg ON isg.immunization_stage_given_id = ci.immunization_stage_given_id "
            "WHERE ci.child_record_id = %s ORDER BY ci.date_given DESC;"
        )
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch immunizations for child record %s", child_record_id)
            return []

    def fetch_breastfeeding_checks(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT bbf_check_id, check_date FROM public.child_breastfeeding_check WHERE child_record_id = %s ORDER BY check_date DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch breastfeeding checks for child record %s", child_record_id)
            return []

    def fetch_iron_supplements(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT child_iron_id, date_started, date_completed, visit_id FROM public.child_iron_supplement_record WHERE child_record_id = %s ORDER BY date_started DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch iron supplements for child record %s", child_record_id)
            return []

    def fetch_screening_assessments(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = (
            "SELECT screening_id, date_assessed, birth_weight, is_low_birth_weight, anemic_seen_date, "
            "anemic_given_iron_date, iron_seen_2_6_mos_date, iron_given_2_6_mos_date, mother_tt_status_id "
            "FROM public.child_screening_assessment WHERE child_record_id = %s ORDER BY date_assessed DESC;"
        )
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch screening assessments for child record %s", child_record_id)
            return []

    def fetch_visits(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT visit_id, visit_no, visit_date, visit_status_id FROM public.child_visit WHERE child_record_id = %s ORDER BY visit_date DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch visits for child record %s", child_record_id)
            return []

    def fetch_visit_schedules(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT child_visit_schedule_id, scheduled_date, scheduled_time, fulfilled_visit_id, status_id, visit_purpose, notes FROM public.child_visit_schedule WHERE child_record_id = %s ORDER BY scheduled_date DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch visit schedules for child record %s", child_record_id)
            return []

    def fetch_feeding_types(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = (
            "SELECT ftns.feeding_type_nwbrn_scrnng_id, ftns.referred_newborn_screening_date, ft.feeding_type_name, ftns.visit_id "
            "FROM public.feeding_type_nwbrn_scrnng ftns LEFT JOIN public.feeding_type ft ON ft.feeding_type_id = ftns.feeding_type_id "
            "WHERE ftns.child_record_id = %s;"
        )
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch feeding types for child record %s", child_record_id)
            return []

    def fetch_vitamin_a(self, child_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT vitamin_a_id, date_given, vit_stage_id, visit_id FROM public.vitamin_a_given WHERE child_record_id = %s ORDER BY date_given DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (child_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch vitamin A records for child record %s", child_record_id)
            return []

    def assemble_report_payload(self, child_record_id: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        payload["patient_info"] = self.fetch_patient_info(child_record_id)
        payload["immunizations"] = self.fetch_immunizations(child_record_id)
        payload["breastfeeding_checks"] = self.fetch_breastfeeding_checks(child_record_id)
        payload["iron_supplements"] = self.fetch_iron_supplements(child_record_id)
        payload["screenings"] = self.fetch_screening_assessments(child_record_id)
        payload["visits"] = self.fetch_visits(child_record_id)
        payload["visit_schedules"] = self.fetch_visit_schedules(child_record_id)
        payload["feeding_types"] = self.fetch_feeding_types(child_record_id)
        payload["vitamin_a"] = self.fetch_vitamin_a(child_record_id)
        return payload
