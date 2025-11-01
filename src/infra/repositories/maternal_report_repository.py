from typing import Any, Dict, List, Optional

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

import logging

logger = logging.getLogger(__name__)


class MaternalReportRepository:
    """Repository layer for assembling data required by maternal health reports.

    Methods intentionally return plain python dicts / lists to keep the service
    layer free to format them into a PDF.
    """

    def __init__(self, ctx: ConnectionAdapter):
        self.ctx = ctx

    def fetch_patient_info(self, maternal_record_id: int) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            m.maternal_record_id,
            p.person_id,
            p.first_name,
            p.last_name,
            p.middle_name,
            p.age,
            p.mobile_num,
            f.family_num,
            m.weight,
            m.height,
            bs.bmi_status_name
        FROM public.maternal_health_record m
        LEFT JOIN public.person p ON p.person_id = m.person_id
        LEFT JOIN public.family_unit f ON f.family_id = m.family_id
        LEFT JOIN public.bmi_status bs ON bs.bmi_status_id = m.bmi_status_id
        WHERE m.maternal_record_id = %s
        LIMIT 1;"""
        try:
            rows = self.ctx.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.exception("Failed to fetch patient info for mhr %s", maternal_record_id)
            return None

    def fetch_pregnancy_summary(self, maternal_record_id: int) -> Dict[str, Any]:
        sql = """
        SELECT
            m.is_transferred,
            ps.lmp,
            ps.edc,
            ts.trimester_stage_name
        FROM public.maternal_health_record m
        LEFT JOIN public.present_pregnancy_status ps ON ps.maternal_record_id = m.maternal_record_id
        LEFT JOIN public.maternal_anc_visit v ON v.maternal_record_id = m.maternal_record_id
        LEFT JOIN public.trimester_stage ts ON ts.trimester_stage_id = v.trimester_stage_id
        WHERE m.maternal_record_id = %s
        LIMIT 1;"""
        try:
            rows = self.ctx.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else {}
        except QueryExecutionException:
            logger.exception("Failed to fetch pregnancy summary for mhr %s", maternal_record_id)
            return {}

    def fetch_medical_and_obstetric_history(self, maternal_record_id: int) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        try:
            mh_sql = "SELECT previous_illness, previous_hospitalization, previous_preg_complication FROM public.medical_history WHERE maternal_record_id = %s LIMIT 1;"
            oh_sql = "SELECT num_children_born_alive, num_children_living, num_abortion, num_stillbirth, num_large_babies, has_diabetes FROM public.obstetric_history WHERE maternal_record_id = %s LIMIT 1;"
            prev_sql = "SELECT date_of_deliveries, outcome, baby_weight FROM public.previous_pregnancy_info WHERE maternal_record_id = %s LIMIT 1;"

            mh = self.ctx.execute_query_to_dict(mh_sql, (maternal_record_id,))
            oh = self.ctx.execute_query_to_dict(oh_sql, (maternal_record_id,))
            prev = self.ctx.execute_query_to_dict(prev_sql, (maternal_record_id,))

            if mh:
                result["medical_history"] = mh[0]
            if oh:
                result["obstetric_history"] = oh[0]
            if prev:
                result["previous_pregnancy"] = prev[0]

        except QueryExecutionException:
            logger.exception("Failed to fetch medical/obstetric history for mhr %s", maternal_record_id)

        return result

    def fetch_lab_results(self, maternal_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT lab_test_id, result, result_img_path, date_tested FROM public.lab_result WHERE maternal_record_id = %s ORDER BY date_tested DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (maternal_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch lab results for mhr %s", maternal_record_id)
            return []

    def fetch_vaccination_records(self, maternal_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT t.tt_id, tt.tt_type_name, t.date_given FROM public.tt_vaccine_record t LEFT JOIN public.tt_type tt ON tt.tt_type_id = t.tt_type_id WHERE t.maternal_record_id = %s ORDER BY t.date_given DESC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (maternal_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch vaccination records for mhr %s", maternal_record_id)
            return []

    def fetch_micronutrients(self, maternal_record_id: int) -> Optional[Dict[str, Any]]:
        sql = "SELECT iron_start_date, iron_end_date, deworming_given_date FROM public.micronutrients WHERE maternal_record_id = %s LIMIT 1;"
        try:
            rows = self.ctx.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except QueryExecutionException:
            logger.exception("Failed to fetch micronutrients for mhr %s", maternal_record_id)
            return None

    def fetch_checklist_findings(self, maternal_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT c.checklist_item_id, ci.checklist_name FROM public.maternal_checklist c LEFT JOIN public.checklist_item ci ON ci.checklist_item_id = c.checklist_item_id WHERE c.maternal_record_id = %s;"
        try:
            return self.ctx.execute_query_to_dict(sql, (maternal_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch checklist findings for mhr %s", maternal_record_id)
            return []

    def assemble_report_payload(self, maternal_record_id: int) -> Dict[str, Any]:
        """Convenience method returning all sections to be used by the service layer."""
        payload: Dict[str, Any] = {}
        payload["patient_info"] = self.fetch_patient_info(maternal_record_id)
        payload["pregnancy_summary"] = self.fetch_pregnancy_summary(maternal_record_id)
        payload.update(self.fetch_medical_and_obstetric_history(maternal_record_id))
        payload["lab_results"] = self.fetch_lab_results(maternal_record_id)
        payload["vaccination_records"] = self.fetch_vaccination_records(maternal_record_id)
        payload["micronutrients"] = self.fetch_micronutrients(maternal_record_id)
        payload["checklist_findings"] = self.fetch_checklist_findings(maternal_record_id)
        return payload
