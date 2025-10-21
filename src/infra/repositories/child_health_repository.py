from child_health.exception.child_health_record_exception import ChildHealthRecordException
from src.app.transfer_objects.request.child_health_version_two.immunization_request import ImmunizationRequestVersion2
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

import logging

logger = logging.getLogger(__name__)


class ChildHealthRepository:

    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def insert_child_immunizations(self, immunization: ImmunizationRequestVersion2):
        sql = """SELECT * FROM add_child_immunization(%s, %s, %s, %s, %s);"""
        params = [
            immunization.p_child_record_id, immunization.p_assessed_by_id,
            immunization.p_immunization_type_id, immunization.p_immunization_stage_given_id,
            immunization.p_date_given
        ]
        try:
            result = self._ctx.execute_query(sql, params)
            if not result:
                return None
            return result
        except QueryExecutionException as e:
            logger.error(f"Error inserting child immunization: {e}")
            if ChildHealthRecordException.is_child_health_record_exception(e.code):
                raise ChildHealthRecordException(e.message) from e
            raise e

    def fetch_immunization_stages_by_chr_id_and_visit_id(self, chr_id: int) -> list[dict]:
        raw = """SELECT immunization_type.immunization_type_id, immunization_type.immunization_type_name, immunization_stage_given.immunization_stage_given_id, immunization_stage_given.immunization_stage_name 
            FROM child_immunization 
            INNER JOIN immunization_type
            ON immunization_type.immunization_type_id = child_immunization.immunization_type_id
            INNER JOIN immunization_stage_given
            ON immunization_stage_given.immunization_stage_given_id = child_immunization.immunization_stage_given_id
            WHERE child_record_id = %s ORDER BY immunization_stage_given.immunization_stage_given_id ASC;"""

        params = [chr_id]
        return self._ctx.execute_query_to_dict(raw, params)

    def fetch_recent_visit_id_by_chr_id(self, chr_id: int) -> int:
        raw = """
            SELECT visit_id FROM child_visit WHERE child_record_id = %s ORDER BY visit_date DESC LIMIT 1;
        """
        params = [chr_id]
        result = self._ctx.execute_query_to_dict(raw, params)
        if result:
            return result[0]['visit_id']
        return None
