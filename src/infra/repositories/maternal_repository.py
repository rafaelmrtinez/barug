from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.app.transfer_objects.response.current_maternal_record_response import CurrentMaternalRecordResponse
from src.app.transfer_objects.response.maternal_entry_child_record_response import MaternalChildRecordEntryResponse
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
        
    def fetch_maternal_record_id_by_child_record_id(self, id: int) -> int | None:
        raw = """
            SELECT maternal_health_record.maternal_record_id
            FROM child_health_record
                INNER JOIN maternal_health_record
                ON maternal_health_record.person_id = child_health_record.mother_id
            WHERE child_record_id = %s;
        """
        params = [id]

        result = self._ctx.execute_query_to_dict(raw, params)

        if not result:
            return None

        return result[0]['maternal_record_id']

    def fetch_maternal_child_record_by_person_record_id_and_maternal_record_id(self, person_record_id: int, maternal_record_id: int) -> MaternalChildRecordEntryResponse | None:
        raw = """
        WITH visit_cte AS (
        SELECT visit_id
        FROM child_visit
        WHERE child_record_id = %s
        ),

        feeding_cte AS (
        SELECT
            fns.visit_id,
            ft.feeding_type_name,
            fns.referred_newborn_screening_date
        FROM feeding_type_nwbrn_scrnng AS fns
        INNER JOIN feeding_type AS ft
            ON ft.feeding_type_id = fns.feeding_type_id
        WHERE fns.visit_id IN (SELECT visit_id FROM visit_cte)
        ),

        bf_check_cte AS (
        SELECT
            visit_id,
            ARRAY_AGG(check_date ORDER BY check_date ASC) AS breastfeeding_check_dates
        FROM child_breastfeeding_check
        WHERE visit_id IN (SELECT visit_id FROM visit_cte)
        GROUP BY visit_id
        ),

        immunization_cte AS (
        SELECT
            ci.visit_id,
            JSON_AGG(
            JSON_BUILD_OBJECT(
                'immunization_type', it.immunization_type_name,
                'dates_given', sub.dates_given
            )
            ) AS immunizations
        FROM child_immunization AS ci
        INNER JOIN immunization_type AS it
            ON it.immunization_type_id = ci.immunization_type_id
        INNER JOIN (
            SELECT
            immunization_type_id,
            visit_id,
            ARRAY_AGG(date_given ORDER BY date_given ASC) AS dates_given
            FROM child_immunization
            GROUP BY immunization_type_id, visit_id
        ) AS sub
            ON sub.immunization_type_id = ci.immunization_type_id
        AND sub.visit_id = ci.visit_id
        WHERE ci.visit_id IN (SELECT visit_id FROM visit_cte)
        GROUP BY ci.visit_id
        ),

        screening_cte AS (
        SELECT
            visit_id,
            is_protected_at_birth,
            date_assessed
        FROM child_screening_assessment
        WHERE visit_id IN (SELECT visit_id FROM visit_cte)
        ),

        iron_supplement_cte AS (
        SELECT
            visit_id,
            date_started,
            date_completed
        FROM child_iron_supplement_record
        WHERE visit_id IN (SELECT visit_id FROM visit_cte)
        ),

        vitamin_cte AS (
        SELECT
            child_record_id,
            JSON_AGG(
            JSON_BUILD_OBJECT('date_given', date_given, 'dose_no', dose_no)
            ORDER BY date_given ASC
            ) AS vitamins_given
        FROM vitamin_a_given
        WHERE child_record_id = %s
        GROUP BY child_record_id
        ),

        monitoring_cte AS (
        SELECT
            visit_id,
            JSON_AGG(
            JSON_BUILD_OBJECT(
                'check_date', check_date,
                'age', age,
                'weight', weight,
                'temperature', temperature,
                'height', height,
                'findings', findings,
                'notes', notes
            ) ORDER BY check_date ASC
            ) AS monitoring_logs
        FROM child_monitoring_log
        WHERE visit_id IN (SELECT visit_id FROM visit_cte)
        GROUP BY visit_id
        ),

        tt_vaccine_cte AS (
        SELECT
            ttr.maternal_record_id,
            tt.tt_type_name AS latest_tt_vaccine
        FROM tt_vaccine_record AS ttr
        INNER JOIN tt_type AS tt
            ON tt.tt_type_id = ttr.tt_type_id
        WHERE ttr.maternal_record_id = %s
        ORDER BY ttr.date_given DESC
        LIMIT 1
        )

        SELECT
        v.visit_id,
        f.feeding_type_name,
        f.referred_newborn_screening_date,
        b.breastfeeding_check_dates,
        s.is_protected_at_birth,
        s.date_assessed,
        i.date_started,
        i.date_completed,
        vit.vitamins_given::jsonb AS vitamins_given,
        m.monitoring_logs::jsonb AS monitoring_logs,
        im.immunizations::jsonb AS immunizations,
        tt.latest_tt_vaccine
        FROM visit_cte v
        LEFT JOIN feeding_cte f ON f.visit_id = v.visit_id
        LEFT JOIN bf_check_cte b ON b.visit_id = v.visit_id
        LEFT JOIN screening_cte s ON s.visit_id = v.visit_id
        LEFT JOIN iron_supplement_cte i ON i.visit_id = v.visit_id
        LEFT JOIN vitamin_cte vit ON vit.child_record_id = %s
        LEFT JOIN monitoring_cte m ON m.visit_id = v.visit_id
        LEFT JOIN immunization_cte im ON im.visit_id = v.visit_id
        LEFT JOIN tt_vaccine_cte tt ON tt.maternal_record_id = %s
        ORDER BY v.visit_id ASC;
        """
        params = [person_record_id, person_record_id, maternal_record_id, person_record_id, maternal_record_id]
        result = self._ctx.execute_query_to_dict(raw, params)
        if not result:
            return None
        return MaternalChildRecordEntryResponse(**result[0])

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
