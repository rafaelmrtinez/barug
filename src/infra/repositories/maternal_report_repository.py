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
            p.birthdate,
            p.age,
            p.mobile_num,
            p.occupation AS patient_occupation,
            f.family_num,
            fu.ufc_num,
            m.weight,
            m.height,
            bs.bmi_status_name,
            -- husband info
            h.person_id AS husband_id,
            (h.first_name || ' ' || COALESCE(h.middle_name, '') || ' ' || h.last_name) AS husband_full_name,
            h.occupation AS husband_occupation,
            -- full address
            TRIM(BOTH ', ' FROM CONCAT_WS(', ', NULLIF(a.street, ''), NULLIF(ps.purok_sitio_name, ''), NULLIF(a.barangay, ''), NULLIF(a.city, ''))) AS address
        FROM public.maternal_health_record m
        LEFT JOIN public.person p ON p.person_id = m.person_id
        LEFT JOIN public.family_unit f ON f.family_id = m.family_id
        LEFT JOIN public.family_unit fu ON fu.family_id = m.family_id
        LEFT JOIN public.addresss a ON a.address_id = p.address_id
        LEFT JOIN public.purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
        LEFT JOIN public.bmi_status bs ON bs.bmi_status_id = m.bmi_status_id
        LEFT JOIN public.person h ON h.person_id = m.husband_id
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
            ps.gravida,
            ps.para,
            ps.is_fullterm,
            ps.is_preterm,
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
            prev_sql = (
                "SELECT ppi.date_of_deliveries, ppi.outcome, ppi.baby_weight, ppi.baby_sex, ppi.ballard_score, ppi.apgar_score, ppi.delivery_type_id, dt.delivery_type_name "
                "FROM public.previous_pregnancy_info ppi LEFT JOIN public.delivery_type dt ON dt.delivery_type_id = ppi.delivery_type_id "
                "WHERE ppi.maternal_record_id = %s ORDER BY ppi.date_of_deliveries DESC LIMIT 1;"
            )

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
        # Note: the `lab_result` table uses `lab_test_id` to reference the
        # type in `lab_test_type` (see sample INSERTs). Join on that column.
        sql = (
            "SELECT l.lab_test_id, l.result, l.result_img_path, l.date_tested, "
            "t.lab_test_type_name "
            "FROM public.lab_result l "
            "LEFT JOIN public.lab_test_type t ON t.lab_test_type_id = l.lab_test_id "
            "WHERE l.maternal_record_id = %s "
            "ORDER BY l.date_tested DESC;"
        )
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

    def fetch_plan_and_baseline(self, maternal_record_id: int) -> Optional[Dict[str, Any]]:
        sql = "SELECT plan_and_baseline_id, new_born_screening_plan, place_of_delivery_plan FROM public.plan_and_baseline WHERE maternal_record_id = %s LIMIT 1;"
        try:
            rows = self.ctx.execute_query_to_dict(sql, (maternal_record_id,))
            return rows[0] if rows else None
        except QueryExecutionException:
            logger.exception("Failed to fetch plan and baseline for mhr %s", maternal_record_id)
            return None

    def fetch_anc_rows(self, maternal_record_id: int) -> List[Dict[str, Any]]:
        sql = "SELECT anc_row_id, anc_visit_id, anc_date, aog_weeks, aog_days, weight_kg, bp_systolic, bp_diastolic, leopolds_findings, notes FROM public.maternal_anc_row WHERE maternal_record_id = %s ORDER BY anc_date ASC;"
        try:
            return self.ctx.execute_query_to_dict(sql, (maternal_record_id,)) or []
        except QueryExecutionException:
            logger.exception("Failed to fetch ANC rows for mhr %s", maternal_record_id)
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
        payload["plan_and_baseline"] = self.fetch_plan_and_baseline(maternal_record_id)
        payload["anc_rows"] = self.fetch_anc_rows(maternal_record_id)
        return payload
