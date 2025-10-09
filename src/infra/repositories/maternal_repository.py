from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.app.transfer_objects.response.current_maternal_record_response import CurrentMaternalRecordResponse
from src.app.transfer_objects.response.maternal_record_basic_history_response import MaternalRecordBasicHistoryResponse
from src.app.transfer_objects.response.previous_maternal_record_response import PreviousMaternalRecordResponse
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.child_visit_exception import ChildVisitException
from src.infra.exceptions.maternal_exceptions import MaternalException
from src.infra.exceptions.query_exec_exception import QueryExecutionException


class MaternalRepository(IMaternalRepository):

    def __init__(self, ctx: IConnectionAdapter) -> None:
        self._ctx = ctx
        
    def fetch_maternal_record_history_by_maternal_record_id(self, id: int) -> MaternalRecordBasicHistoryResponse:
        raw = """
        SELECT
        mav.visit_date AS visit_date,
        ts.trimester_stage_name AS trimester,
        pab.weight,
        COALESCE(STRING_AGG(DISTINCT rc.risk_category_name, ', '), '') AS danger_signs
        FROM maternal_anc_visit AS mav
        INNER JOIN maternal_health_record AS mhr
        ON mhr.maternal_record_id = mav.maternal_record_id
        INNER JOIN trimester_stage AS ts
        ON ts.trimester_stage_id = mav.trimester_stage_id
        LEFT JOIN plan_and_baseline AS pab
        ON pab.anc_visit_id = mav.anc_visit_id
        LEFT JOIN risk_response AS rr
        ON rr.anc_visit_id = mav.anc_visit_id
        LEFT JOIN risk_category AS rc
        ON rc.risk_category_id = rr.risk_category_id
        WHERE mhr.maternal_record_id = %s
        GROUP BY
        mav.visit_date,
        ts.trimester_stage_name,
        pab.weight
        ORDER BY mav.visit_date DESC OFFSET 1;"""
        
        params = [id]
        
        result = self._ctx.execute_query_to_dict(raw, params)
        
        if not result:
            return []
        
        return [MaternalRecordBasicHistoryResponse(**record) for record in result]

    def fetch_family_number_by_person_id(self, id: int) -> int | None:
        raw = """
            SELECT family_unit.family_num FROM house_member 
                INNER JOIN person
            ON person.person_id = house_member.person_id
                INNER JOIN family_unit
            ON family_unit.family_id = house_member.family_id
            WHERE person.person_id = %s;
        """
        params = [id]

        result = self._ctx.execute_query_to_dict(raw, params)

        if not result:
            return None

        return result[0]['family_num']

    def fetch_previous_maternal_record_by_maternal_visit_id(self, id: int) -> PreviousMaternalRecordResponse | None:
        raw = """
            SELECT
            mav.visit_date,
            ts.trimester_stage_name,
            pab.weight,
            bs.bmi_status_name,
            COALESCE(STRING_AGG(DISTINCT rc.risk_category_name, ', '), '') AS danger_signs
            FROM maternal_anc_visit AS mav
            INNER JOIN maternal_health_record AS mhr
            ON mhr.maternal_record_id = mav.maternal_record_id
            INNER JOIN trimester_stage AS ts
            ON ts.trimester_stage_id = mav.trimester_stage_id
            LEFT JOIN plan_and_baseline AS pab
            ON pab.anc_visit_id = mav.anc_visit_id
            LEFT JOIN bmi_status AS bs
            ON bs.bmi_status_id = pab.bmi_status_id
            LEFT JOIN risk_response AS rr
            ON rr.anc_visit_id = mav.anc_visit_id
            LEFT JOIN risk_category AS rc
            ON rc.risk_category_id = rr.risk_category_id
            WHERE mhr.maternal_record_id = %s
            GROUP BY
            mav.visit_date,
            ts.trimester_stage_name,
            pab.weight,
            bs.bmi_status_name
            ORDER BY mav.visit_date DESC
            LIMIT 1 OFFSET 1;
        """

        params = [id]
        result = self._ctx.execute_query_to_dict(raw, params)

        if not result:
            return None

        return PreviousMaternalRecordResponse(**result[0])

    def fetch_current_maternal_record_by_maternal_visit_id(self, id: int) -> CurrentMaternalRecordResponse | None:
        raw = """
            SELECT
            person.person_id,
            CONCAT(
                person.first_name, ' ',
                COALESCE(person.middle_name, ''), ' ',
                person.last_name, ' ',
                COALESCE(person.suffix, '')
            ) AS full_name,
            mav.visit_date,
            mhr.maternal_record_id,
            ts.trimester_stage_name,
            pab.weight,
            pab.place_of_delivery_plan,
            pab.new_born_screening_plan,
            pab.height,
            bs.bmi_status_name,
            pps.lmp,
            pps.edc,
            COALESCE(STRING_AGG(DISTINCT rc.risk_category_name, ', '), '') AS danger_signs
            FROM maternal_anc_visit AS mav
            INNER JOIN maternal_health_record AS mhr
            ON mhr.maternal_record_id = mav.maternal_record_id
            INNER JOIN trimester_stage AS ts
            ON ts.trimester_stage_id = mav.trimester_stage_id
            LEFT JOIN plan_and_baseline AS pab
            ON pab.anc_visit_id = mav.anc_visit_id
            LEFT JOIN bmi_status AS bs
            ON bs.bmi_status_id = pab.bmi_status_id
            INNER JOIN person AS person
            ON person.person_id = mhr.person_id
            LEFT JOIN present_pregnancy_status AS pps
            ON pps.anc_visit_id = mav.anc_visit_id
            LEFT JOIN risk_response AS rr
            ON rr.anc_visit_id = mav.anc_visit_id
            LEFT JOIN risk_category AS rc
            ON rc.risk_category_id = rr.risk_category_id
            WHERE mhr.maternal_record_id = %s
            GROUP BY
            person.person_id, full_name, mav.visit_date,
            mhr.maternal_record_id, ts.trimester_stage_name,
            pab.weight, pab.place_of_delivery_plan,
            pab.new_born_screening_plan, pab.height,
            bs.bmi_status_name, pps.lmp, pps.edc
            ORDER BY mav.visit_date DESC LIMIT 1;
        """
        params = [id]

        result = self._ctx.execute_query_to_dict(raw, params)

        if not result:
            return None

        return CurrentMaternalRecordResponse(**result[0])

    def fetch_immunization_stage_by_child_health_record_id(self, child_health_record_id: int) -> dict | None:
        raw = """
        SELECT immunization_stage_given.immunization_stage_name AS stage  FROM child_immunization
        INNER JOIN immunization_stage_given
        ON immunization_stage_given.immunization_stage_given_id = child_immunization.immunization_stage_given_id
        WHERE child_record_id = %s;"""
        params = [child_health_record_id]
        return self._ctx.execute_query_to_dict(raw, params)[0] if self._ctx.execute_query_to_dict(raw, params) else None

    def fetch_immunization_type_id_by_type_name(self, immunization_type_name: str) -> int:
        raw = """
            SELECT immunization_type_id FROM immunization_type WHERE immunization_type_name = %s;
        """
        params = [immunization_type_name]
        result = self._ctx.execute_query_to_dict(raw, params)
        return result[0]['immunization_type_id'] if result else 0

    def fetch_child_record_by_person_id(self, person_id: int) -> int:
        raw = """
            SELECT child_record_id FROM child_health_record WHERE person_id = %s;
        """
        params = [person_id]
        return self._ctx.execute_query_to_dict(raw, params)[0]['child_record_id']

    def insert_child_visit(self, data: ChildVisitRequest):
        try:
            raw = """
                SELECT * FROM insert_child_visit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            params = [
                data.p_child_record_id,
                data.p_assessed_by_id,
                data.p_visit_date,
                data.p_feeding_type_id,
                data.p_referred_nbs_date,
                data.p_child_immunizations,
                data.p_bf_checks,
                data.p_monitoring_logs,
                data.p_screening,
                data.p_iron_supplements,
                data.p_vitamin_a
            ]

            row = self._ctx.execute_query(raw, params)

            if not row:
                raise RuntimeError("No ID returned from insert_child_visit")

            return row[0][0]

        except QueryExecutionException as e:
            if ChildVisitException.is_child_visit_exception(e.code):
                raise ChildVisitException(e.message) from e
            raise

    def insert_child_record(self, request: CreateChildRecordRequest) -> int:
        try:
            cmd = """
            SELECT * FROM create_child_health_record(%s, %s, %s, %s, %s, %s, %s); 
            """
            row = self._ctx.execute_query(cmd, [
                request.p_staff_id,
                request.p_person_id,
                request.p_mother_id,
                request.p_father_id,
                request.p_birth_order,
                request.p_delivery_place_type_id,
                request.p_family_id
            ])

            if not row:
                raise RuntimeError(
                    "No ID returned from create_child_health_record")

            return row[0]
        except QueryExecutionException as e:
            if MaternalException.is_maternal_exception(e.code):
                raise MaternalException(e.message) from e
