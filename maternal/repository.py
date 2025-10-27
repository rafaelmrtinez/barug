from psycopg2.extras import Json

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException
import logging

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


class MaternalHealthRecordRepository:

    def __init__(self, ctx: ConnectionAdapter):
        self.ctx = ctx

    def insert_anc_row_findings(self, mhr_id, staff_id, aog_weeks, aog_days, weight, bp_systolic, bp_diastolic):
        sql = """SELECT * FROM _get_or_create_today_maternal_visit(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::NUMERIC, %s::INTEGER, %s::INTEGER);"""
        params = (mhr_id, staff_id, aog_weeks, aog_days, weight, bp_systolic, bp_diastolic)
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting ANC row findings: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def update_maternal_anc_row_findings(self, mhr_id, staff_id, findings, notes):
        sql = """SELECT * FROM update_maternal_anc_row_findings(%s::INTEGER, %s::INTEGER, %s::TEXT, %s::TEXT);"""
        params = (mhr_id, staff_id, findings, notes)
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error updating maternal ANC row findings: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def insert_maternal_lab_results(self, mhr_id, staff_id, lab_results):
        sql="""SELECT * FROM add_maternal_lab_results_json(%s::INTEGER, %s::INTEGER, %s::JSONB);"""
        params = (mhr_id, staff_id, Json(lab_results))
        print(f'INSERT LAB RESULTS PARAMS: {params}')
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting maternal lab results: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def insert_present_pregnancy_status(self, mhr_id, staff_id, gravida, para, is_fullterm, is_preterm, lmp, edc):
        sql = """SELECT * FROM insert_present_pregnancy_status(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::BOOLEAN, %s::BOOLEAN, %s::DATE, %s::DATE);"""
        params = (
            mhr_id, staff_id, gravida, para, is_fullterm, is_preterm, lmp, edc
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting present pregnancy status: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e
        
    def insert_previous_pregnancy_info(self, mhr_id, staff_id, date_of_delivery, outcome, baby_weight_kg, ballard_score, apgar_score, delivery_type_id, sex):
        # Note: keep SQL parameter order in sync with the DB function signature.
        sql = """SELECT * FROM insert_previous_pregnancy_info(%s::INTEGER, %s::INTEGER, %s::DATE, %s::TEXT, %s::NUMERIC, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER);"""
        params = (
            mhr_id, staff_id, date_of_delivery, outcome, baby_weight_kg, ballard_score, apgar_score, delivery_type_id, sex
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting previous pregnancy info: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e
        
    def fetch_micronutrients_by_mhr_id(self, maternal_record_id: int):
        """
        Return the most recent micronutrients row for a maternal record (if any).
        Fields returned:
          - iron_start_date
          - iron_end_date
          - deworming_date (alias for deworming_given_date)
        """
        sql = """
            SELECT
                m.iron_start_date   AS iron_start_date,
                m.iron_end_date     AS iron_end_date,
                m.deworming_given_date AS deworming_date
            FROM public.micronutrients AS m
            WHERE m.maternal_record_id = %s
            ORDER BY m.micronutrients_id DESC
            LIMIT 1;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def insert_micronutrients(self, mhr_id, staff_id, iron_started, iron_completed, deworming_started):
        sql = """SELECT * FROM insert_micronutrients(%s::INTEGER, %s::INTEGER, %s::DATE, %s::DATE, %s::DATE);"""
        params = (
            mhr_id, staff_id, iron_started, iron_completed, deworming_started
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting micronutrients: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def insert_plan_and_baseline(self, mhr_id, staff_id, nbs_plan, delivery_plan):
        sql = """SELECT * FROM insert_plan_and_baseline(%s::INTEGER, %s::INTEGER, %s::BOOLEAN, %s::TEXT);"""
        params = (
            mhr_id, staff_id, nbs_plan, delivery_plan
        )
        logger.debug("Insert plan and baseline params: %s", params)
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting plan and baseline: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def fetch_checklist_items(self):
        """Return all checklist items as list of dicts: [{'checklist_item_id': int, 'checklist_name': str}, ...]"""
        sql = """
            SELECT checklist_item_id, checklist_name
            FROM public.checklist_item
            ORDER BY checklist_item_id;
        """
        try:
            rows = self.ctx.execute_query_to_dict(sql, ())
            return rows or []
        except QueryExecutionException as e:
            logger.error("Error fetching checklist items: %s",
                         getattr(e, "message", e))
            raise

    def fetch_maternal_checklist_by_mhr_id(self, maternal_record_id: int):
        """Return checklist_item_id ints for a given maternal_record_id."""
        sql = """
            SELECT checklist_item_id
            FROM public.maternal_checklist
            WHERE maternal_record_id = %s
            ORDER BY maternal_checklist_id;
        """
        try:
            rows = self.ctx.execute_query_to_dict(sql, (maternal_record_id,))
            return [r.get("checklist_item_id") for r in (rows or [])]
        except QueryExecutionException as e:
            logger.error("Error fetching maternal checklist for mhr %s: %s",
                         maternal_record_id, getattr(e, "message", e))
            raise

    def insert_checklist_items(self, mhr_id, staff_id, checklist_items):
        sql = """SELECT * FROM add_maternal_checklist_items_json(%s::INTEGER, %s::INTEGER, %s::JSONB);"""

        # normalize input: accept either a flat list or a list-of-lists (common from form cleaning)
        items = checklist_items
        if isinstance(checklist_items, list) and len(checklist_items) == 1 and isinstance(checklist_items[0], list):
            items = checklist_items[0]

        # convert to integers and validate
        try:
            items_int = [int(x) for x in items]
        except (TypeError, ValueError):
            raise ValueError("checklist_items must be convertible to integers")

        if not items_int:
            raise ValueError("checklist_items must be a non-empty list of ids")

        params = (mhr_id, staff_id, Json(items_int))
        logger.debug("Insert checklist params: %s", params)
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(
                f"Error inserting maternal checklist items: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def fetch_maternal_tt_by_mhr_id(self, id: int):
        sql = """SELECT tt_type.tt_type_id,  tt_type.tt_type_name FROM tt_vaccine_record 
            INNER JOIN tt_type
            ON tt_type.tt_type_id = tt_vaccine_record.tt_type_id
            WHERE maternal_record_id = %s;"""
        params = (id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows

    def insert_maternal_tt_record(self, mhr_id, staff_id, tt_type_id, date_given):
        sql = """SELECT * FROM add_maternal_tt_record(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::DATE);"""
        params = (
            mhr_id, staff_id, tt_type_id, date_given
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting maternal TT record: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def fetch_medical_history_by_mhr_id(self, maternal_record_id: int):
        sql = """
            SELECT
                mh.previous_illness,
                mh.previous_hospitalization,
                mh.previous_preg_complication
            FROM
                medical_history AS mh
            WHERE
                mh.maternal_record_id = %s
            ORDER BY
                mh.medical_history_id DESC
            LIMIT 1;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def insert_medical_history(
            self, mhr_id, staff_id, previous_illness,
            previous_hostpitalzation, previous_complication):
        sql = """SELECT * FROM insert_medical_history(%s::INTEGER, %s::INTEGER, %s::TEXT, %s::TEXT, %s::TEXT);"""
        params = (
            mhr_id, staff_id, previous_illness, previous_hostpitalzation, previous_complication
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting medical history: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def fetch_obstetric_history_by_mhr_id(self, maternal_record_id: int):
        sql = """
            SELECT
                oh.num_children_born_alive,
                oh.num_children_living,
                oh.num_abortion,
                oh.num_stillbirth,
                oh.num_large_babies,
                oh.has_diabetes
            FROM
                obstetric_history AS oh
            WHERE
                oh.maternal_record_id = %s;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def insert_obstetric_history(
            self, mhr_id: int, added_by_id: int, num_children_born_alive: int,
            num_children_living: int, num_of_abortions: int, num_stillbirth: int, num_large_babies: int,
            has_diabetes: bool):
        sql = """SELECT * FROM insert_obstetric_history(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::INTEGER, %s::BOOLEAN);"""
        params = (
            mhr_id, added_by_id, num_children_born_alive, num_children_living,
            num_of_abortions, num_stillbirth, num_large_babies, has_diabetes
        )
        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting obstetric history: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e

    def insert_maternal_health_record(self, staff_id, person_id, husband_id, weight, height, bmi_status_id, is_transferred):
        sql = """SELECT * FROM create_maternal_health_record_bhw(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::DECIMAL, %s::DECIMAL, %s::INTEGER, %s::BOOLEAN);"""
        params = (
            staff_id, person_id, husband_id, weight,
            height, bmi_status_id, is_transferred)

        try:
            rows = self.ctx.execute_query(sql, params)
            return rows[0] if rows else None
        except QueryExecutionException as e:
            logger.error(f"Error inserting child health record: {e.message}")
            if MaternalHealthRecordException.is_maternal_health_record_exception(e.code):
                raise MaternalHealthRecordException(e.message) from e
            raise e
        except Exception as e:
            logger.error(
                f"Unexpected error inserting maternal health record: {e}")
            raise e

    def fetch_mother_basic_info_by_person_id(self, id: int):
        sql = """
            SELECT 
                f.family_num AS family_number,
                p.birthdate AS date_of_birth,
                p.age,
                pk.dst_person_id AS spouse_id,
                CONCAT(s.first_name, ' ', s.last_name) AS spouse_name,
                s.occupation AS spouse_occupation
            FROM person p
            LEFT JOIN house_member hm ON hm.person_id = p.person_id
            LEFT JOIN family_unit f ON f.family_id = hm.family_id
            LEFT JOIN person_kinship pk 
                ON pk.src_person_id = p.person_id
            LEFT JOIN relationship r 
                ON r.relationship_id = pk.relationship_id
                AND LOWER(r.relationship_name) = 'spouse'
            LEFT JOIN person s 
                ON s.person_id = pk.dst_person_id
            WHERE p.person_id = %s
            ORDER BY pk.added_at DESC
            LIMIT 1;
        """
        params = (id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_risk_codes_by_mhr_id(self, maternal_record_id: int):
        sql = """
        WITH cat_map AS (
        SELECT 1 AS ord, 'OBSTETRIC RISKS'::text AS category UNION ALL
        SELECT 2,         'MEDICAL CONDITIONS'::text
        ),
        hits AS (
        SELECT DISTINCT
            CASE
            WHEN rc.risk_category_name ILIKE %s THEN 'OBSTETRIC RISKS'
            WHEN rc.risk_category_name ILIKE %s THEN 'MEDICAL CONDITIONS'
            ELSE NULL
            END AS category
        FROM public.maternal_anc_visit AS mav
        JOIN public.risk_response      AS rr ON rr.anc_visit_id = mav.anc_visit_id
        JOIN public.risk_category      AS rc ON rc.risk_category_id = rr.risk_category_id
        WHERE mav.maternal_record_id = %s
        )
        SELECT
        cm.category,
        (h.category IS NOT NULL) AS is_present
        FROM cat_map AS cm
        LEFT JOIN hits AS h
        ON h.category = cm.category
        ORDER BY cm.ord;
        """
        params = ('obstetric%', 'medical%', int(maternal_record_id))
        return self.ctx.execute_query_to_dict(sql, params)

    def fetch_single_micro_nutrients_by_mhr_id(self, maternal_record_id: int):
        sql = """SELECT DISTINCT ON (m.maternal_record_id)
                m.maternal_record_id,
                m.iron_start_date   AS iron_folic_start,
                m.iron_end_date     AS iron_folic_end,
                m.deworming_given_date AS deworming_date
            FROM public.micronutrients AS m
            WHERE m.maternal_record_id = %s
            AND (m.iron_start_date IS NOT NULL
                OR m.iron_end_date IS NOT NULL
                OR m.deworming_given_date IS NOT NULL)
            ORDER BY
            m.maternal_record_id,
            m.micronutrients_id DESC;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_person_id_by_maternal_record_id(self, maternal_record_id: int):
        sql = """SELECT person_id
            FROM public.maternal_health_record
            WHERE maternal_record_id = %s
            LIMIT 1;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0]['person_id'] if rows else None

    def fetch_multiple_micro_nutrients_by_mhr_id(self, maternal_record_id: int):
        sql = """SELECT
            m.micronutrients_id,
            m.maternal_record_id,
            m.anc_visit_id,
            m.iron_start_date,
            m.iron_end_date,
            m.deworming_given_date
            FROM public.micronutrients AS m
            WHERE m.maternal_record_id = %s
            ORDER BY
            GREATEST(
                COALESCE(m.iron_end_date,        DATE '-infinity'),
                COALESCE(m.iron_start_date,      DATE '-infinity'),
                COALESCE(m.deworming_given_date, DATE '-infinity')
            ) DESC,
            m.micronutrients_id DESC
            LIMIT 2;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows

    def fetch_nbs_data_by_mhr_id(self, maternal_record_id: int):
        """
        Return the most recent new_born_screening_plan and place_of_delivery_plan
        for a given maternal_record_id from the plan_and_baseline table.

        Returns a dict like:
            { 'new_born_screening_plan': bool, 'place_of_delivery_plan': str }
        or None if no row exists.
        """
        sql = """
                SELECT new_born_screening_plan, place_of_delivery_plan
                FROM public.plan_and_baseline
                WHERE maternal_record_id = %s
                ORDER BY plan_and_baseline_id DESC
                LIMIT 1;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_lab_results_by_mhr_id(self, maternal_record_id: int):
        """Fetch lab results for a maternal record joined with lab test type name.

        Returns a list of dicts with keys:
            - lab_result_id
            - result
            - date_test (date)
            - result_img_path (stored JSON/text)
            - maternal_record_id
            - lab_test_type_name

        Ordered by date_test DESC, then lab_result_id DESC.
        """
        sql = """
            SELECT
                r.lab_result_id,
                r.lab_test_id,
                r.result,
                r.date_tested::date AS date_test,
                r.result_img_path,
                r.maternal_record_id,
                t.lab_test_type_name
            FROM public.lab_result r
            LEFT JOIN public.lab_test_type t
                ON t.lab_test_type_id = r.lab_test_id
            WHERE r.maternal_record_id = %s
            ORDER BY r.date_tested DESC NULLS LAST, r.lab_result_id DESC;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows or []

    def fetch_prenatal_information_by_mhr_id(self, maternal_record_id: int):
        """Fetch prenatal ANC rows for a maternal record.

        Returns a list of dicts with keys:
            - date (anc_date::date)
            - aog_days
            - aog_weeks
            - weight (weight_kg)
            - bp_systolic
            - bp_diastolic
            - leopolds_findings
            - notes

        Ordered by anc_date DESC then anc_row_id DESC.
        """
        sql = """
            SELECT
                anc_date::date AS date,
                aog_days,
                aog_weeks,
                weight_kg AS weight,
                bp_systolic,
                bp_diastolic,
                leopolds_findings,
                notes
            FROM public.maternal_anc_row
            WHERE maternal_record_id = %s
            ORDER BY anc_date DESC NULLS LAST, anc_row_id DESC;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows or []

    def fetch_delivery_plan_by_mhr_id(self, maternal_record_id: int):
        sql = """SELECT DISTINCT ON (mav.maternal_record_id)
            mav.maternal_record_id,
            pab.place_of_delivery_plan,          -- text
            pab.new_born_screening_plan          -- boolean
        FROM public.maternal_anc_visit AS mav
        JOIN public.plan_and_baseline  AS pab
        ON pab.anc_visit_id = mav.anc_visit_id
        WHERE mav.maternal_record_id = %s
        AND COALESCE(TRIM(pab.place_of_delivery_plan), '') <> ''  -- optional filter
        ORDER BY mav.maternal_record_id,
                mav.visit_date DESC NULLS LAST,
                pab.plan_and_baseline_id DESC;
            """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows

    def fetch_latest_laboratory_results_by_mhr_id(self, maternal_record_id: int):
        sql = """
        WITH latest_visit AS (
        SELECT DISTINCT ON (v.maternal_record_id)
                v.anc_visit_id,
                v.maternal_record_id,
                v.visit_no,
                v.visit_date::date
        FROM public.maternal_anc_visit v
        WHERE v.maternal_record_id = %s
        ORDER BY v.maternal_record_id, v.visit_date DESC, v.anc_visit_id DESC
        ),
        labs_raw AS (
        SELECT
            lv.anc_visit_id,
            t.lab_test_type_name,
            r.result,
            r.date_tested::date AS date_tested,
            r.lab_result_id
        FROM latest_visit lv
        LEFT JOIN public.lab_result r
            ON r.anc_visit_id = lv.anc_visit_id
        LEFT JOIN public.lab_test_type t
            ON t.lab_test_type_id = r.lab_test_id
        ),
        labs_ranked AS (
        SELECT
            lr.*,
            ROW_NUMBER() OVER (
            PARTITION BY lr.lab_test_type_name
            ORDER BY lr.date_tested DESC NULLS LAST, lr.lab_result_id DESC
            ) AS rn
        FROM labs_raw lr
        )
        SELECT
        lv.anc_visit_id,
        lv.maternal_record_id,
        lv.visit_no,
        lv.visit_date,

        -- Urinalysis
        MAX(CASE WHEN l.lab_test_type_name ILIKE 'urinalysis%%' AND l.rn = 1 THEN l.result END)      AS urinalysis_result,
        MAX(CASE WHEN l.lab_test_type_name ILIKE 'urinalysis%%' AND l.rn = 1 THEN l.date_tested END) AS urinalysis_date,

        -- CBC
        MAX(CASE WHEN l.lab_test_type_name ILIKE 'cbc%%' AND l.rn = 1 THEN l.result END)      AS cbc_result,
        MAX(CASE WHEN l.lab_test_type_name ILIKE 'cbc%%' AND l.rn = 1 THEN l.date_tested END) AS cbc_date,

        -- SGOT/SGPT
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%sgot%%' OR l.lab_test_type_name ILIKE '%%sgpt%%') AND l.rn = 1 THEN l.result END)      AS sgot_sgpt_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%sgot%%' OR l.lab_test_type_name ILIKE '%%sgpt%%') AND l.rn = 1 THEN l.date_tested END) AS sgot_sgpt_date,

        -- Creatinine serum
        MAX(CASE WHEN l.lab_test_type_name ILIKE '%%creatinine%%' AND l.rn = 1 THEN l.result END)      AS creatinine_serum_result,
        MAX(CASE WHEN l.lab_test_type_name ILIKE '%%creatinine%%' AND l.rn = 1 THEN l.date_tested END) AS creatinine_serum_date,

        -- BUA / BUN
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%bua%%' OR l.lab_test_type_name ILIKE '%%bun%%') AND l.rn = 1 THEN l.result END)      AS bua_bun_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%bua%%' OR l.lab_test_type_name ILIKE '%%bun%%') AND l.rn = 1 THEN l.date_tested END) AS bua_bun_date,

        -- Syphilis
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%syphilis%%' OR l.lab_test_type_name ILIKE '%%vdrl%%' OR l.lab_test_type_name ILIKE '%%rpr%%') AND l.rn = 1 THEN l.result END)      AS syphilis_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%syphilis%%' OR l.lab_test_type_name ILIKE '%%vdrl%%' OR l.lab_test_type_name ILIKE '%%rpr%%') AND l.rn = 1 THEN l.date_tested END) AS syphilis_date,

        -- HIV
        MAX(CASE WHEN l.lab_test_type_name ILIKE '%%hiv%%' AND l.rn = 1 THEN l.result END)      AS hiv_result,
        MAX(CASE WHEN l.lab_test_type_name ILIKE '%%hiv%%' AND l.rn = 1 THEN l.date_tested END) AS hiv_date,

        -- Hepatitis B
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%hepa%%b%%' OR l.lab_test_type_name ILIKE '%%hepatitis b%%') AND l.rn = 1 THEN l.result END)      AS hepa_b_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%hepa%%b%%' OR l.lab_test_type_name ILIKE '%%hepatitis b%%') AND l.rn = 1 THEN l.date_tested END) AS hepa_b_date,

        -- Blood typing
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%blood%%typing%%' OR l.lab_test_type_name ILIKE '%%abo%%' OR l.lab_test_type_name ILIKE '%%rh%%') AND l.rn = 1 THEN l.result END)      AS blood_typing_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%blood%%typing%%' OR l.lab_test_type_name ILIKE '%%abo%%' OR l.lab_test_type_name ILIKE '%%rh%%') AND l.rn = 1 THEN l.date_tested END) AS blood_typing_date,

        -- OGCT (50g, 24–28 wks)
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%ogct%%' OR l.lab_test_type_name ILIKE '%%gct%%50%%') AND l.rn = 1 THEN l.result END)      AS ogct_50g_result,
        MAX(CASE WHEN (l.lab_test_type_name ILIKE '%%ogct%%' OR l.lab_test_type_name ILIKE '%%gct%%50%%') AND l.rn = 1 THEN l.date_tested END) AS ogct_50g_date

        FROM latest_visit lv
        LEFT JOIN labs_ranked l ON l.anc_visit_id = lv.anc_visit_id
        GROUP BY lv.anc_visit_id, lv.maternal_record_id, lv.visit_no, lv.visit_date;
        """
        params = (int(maternal_record_id),)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows or None

    def fetch_latest_present_pregnancy_by_mhr_id(self, maternal_record_id: int):
        sql = """WITH latest_visit AS (
            SELECT DISTINCT ON (v.maternal_record_id)
                    v.anc_visit_id,
                    v.maternal_record_id,
                    v.visit_no,
                    v.visit_date::date,
                    v.trimester_stage_id,
                    v.assessed_by_id
            FROM public.maternal_anc_visit AS v
            WHERE v.maternal_record_id = %s
            ORDER BY v.maternal_record_id, v.visit_date DESC, v.anc_visit_id DESC
            )
            SELECT
            lv.anc_visit_id,
            lv.maternal_record_id,
            lv.visit_no,
            lv.visit_date,
            lv.trimester_stage_id,
            lv.assessed_by_id,
            -- Present pregnancy (may be NULL if not recorded)
            pps.gravida,
            pps.para,
            pps.is_fullterm,
            pps.is_preterm,
            pps.lmp,
            pps.edc
            FROM latest_visit AS lv
            LEFT JOIN public.present_pregnancy_status AS pps
            ON pps.anc_visit_id = lv.anc_visit_id;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_maternal_tt_by_mhr_id(self, maternal_record_id: int):
        sql = """
            SELECT
                r.tt_id,
                t.tt_type_name,
                r.date_given::date AS date_given
            FROM public.tt_vaccine_record AS r
            JOIN public.tt_type AS t
                ON t.tt_type_id = r.tt_type_id
            WHERE r.maternal_record_id = %s
            ORDER BY r.date_given NULLS LAST, r.tt_id DESC;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows or []

    def fetch_all_previous_pregnancies_by_person_id(self, person_id: int):
        sql = """SELECT
            m.maternal_record_id,
            ppi.date_of_deliveries                    AS date_of_delivery,
            ppi.outcome                               AS outcome_type,
            ROUND(ppi.baby_weight::numeric, 2)        AS baby_weight_kg,
            CASE ppi.baby_sex
                WHEN 1 THEN 'Male'
                WHEN 2 THEN 'Female'
                ELSE NULL
            END                                       AS gender,
            ppi.ballard_score                         AS ballard,
            ppi.apgar_score                           AS apgar,
            dt.delivery_type_name                     AS delivery_type
            FROM public.maternal_health_record AS m
            JOIN public.previous_pregnancy_info AS ppi
            ON ppi.maternal_record_id = m.maternal_record_id
            LEFT JOIN public.delivery_type AS dt
            ON dt.delivery_type_id = ppi.delivery_type_id
            WHERE m.person_id = %s
            ORDER BY ppi.date_of_deliveries DESC NULLS LAST,
                    ppi.previous_pregnancy_info_id DESC;"""

        params = (person_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows

    def fetch_all_mhr_form_basic_info_by_mhr_id(self, maternal_record_id: int):
        sql = """
            SELECT
                mhr.maternal_record_id,
                fu.family_num AS family_number,
                CONCAT(mother.first_name, ' ',
                    COALESCE(mother.middle_name, ''), ' ',
                    mother.last_name) AS mother_full_name,
                mother.birthdate AS mother_birthdate,
                DATE_PART('year', AGE(CURRENT_DATE, mother.birthdate)) AS mother_age,
                CONCAT(addr.street, ', ', addr.barangay, ', ', addr.city) AS mother_address,
                CONCAT(husband.first_name, ' ',
                    COALESCE(husband.middle_name, ''), ' ',
                    husband.last_name) AS husband_full_name,
                mother.occupation AS mother_occupation,
                mhr.weight AS mother_weight,
                mhr.height AS mother_height,
                ROUND(mhr.weight / POWER(mhr.height / 100, 2), 2) AS mother_bmi,
                bs.bmi_status_name AS bmi_status
            FROM
                maternal_health_record mhr
                INNER JOIN person AS mother ON mhr.person_id = mother.person_id
                INNER JOIN person AS husband ON mhr.husband_id = husband.person_id
                INNER JOIN family_unit AS fu ON mhr.family_id = fu.family_id
                INNER JOIN addresss AS addr ON mother.address_id = addr.address_id
                INNER JOIN bmi_status AS bs ON mhr.bmi_status_id = bs.bmi_status_id
            WHERE
                mhr.maternal_record_id = %s
            ORDER BY
                fu.family_num;
        """
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_all_maternal_records_for_person(self, person_id: int):
        sql = """
            WITH all_mhr AS (
                SELECT
                    m.maternal_record_id,
                    m.person_id,
                    m.created_at::date AS start_date,
                    m.record_status_id
                FROM public.maternal_health_record m
                WHERE m.person_id = %s
            ),
            latest_visit AS (
                SELECT DISTINCT ON (v.maternal_record_id)
                    v.maternal_record_id, 
                    v.anc_visit_id, 
                    v.visit_date
                FROM public.maternal_anc_visit v
                JOIN all_mhr a ON a.maternal_record_id = v.maternal_record_id
                ORDER BY v.maternal_record_id, v.visit_date DESC, v.anc_visit_id DESC
            )
            SELECT
                a.maternal_record_id,
                a.start_date,
                rs.record_status_name AS status_name
            FROM all_mhr a
            LEFT JOIN latest_visit lv 
                ON lv.maternal_record_id = a.maternal_record_id
            LEFT JOIN public.record_status rs
                ON rs.record_status_id = a.record_status_id
            ORDER BY a.start_date DESC, a.maternal_record_id DESC;
            """
        return self.ctx.execute_query_to_dict(sql, (person_id,)) or []

    def fetch_maternal_health_record_id_by_person_id(self, id: int):
        sql = """SELECT maternal_record_id FROM maternal_health_record WHERE person_id = %s;"""
        params = (id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_maternal_health_record_id_by_person_id(self, id: int):
        sql = """SELECT maternal_record_id FROM maternal_health_record WHERE person_id = %s;"""
        params = (id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_mhr_count_and_fam_id_by_person_id(self, id: int):
        sql = """SELECT 
                    COUNT(mhr.maternal_record_id) AS total_maternal_records,
                    fu.family_num AS family_number
                FROM public.maternal_health_record AS mhr
                LEFT JOIN public.family_unit AS fu
                    ON fu.family_id = mhr.family_id
                WHERE mhr.person_id = %s
                GROUP BY fu.family_num
                LIMIT 1;
                """
        params = (id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_latest_maternal_record_by_person_and_maternal_id(self, person_id: int, maternal_record_id: int):
        """ 
            Mark as deprecated 
        """
        logger.warning("THIS WILL BE DEPRECATED SOON.")
        sql = """WITH target AS (
            SELECT m.maternal_record_id, m.person_id
            FROM public.maternal_health_record m
            WHERE m.person_id = %s AND m.maternal_record_id = %s
            ),
            latest_visit AS (
            SELECT DISTINCT ON (v.maternal_record_id)
                    v.maternal_record_id, v.anc_visit_id, v.visit_date
            FROM public.maternal_anc_visit v
            JOIN target t ON t.maternal_record_id = v.maternal_record_id
            ORDER BY v.maternal_record_id, v.visit_date DESC, v.anc_visit_id DESC
            )
            SELECT
            p.person_id,
            t.maternal_record_id,
            TRIM(REGEXP_REPLACE(CONCAT_WS(' ',
                COALESCE(p.first_name,''), NULLIF(LEFT(COALESCE(p.middle_name,''),1)||'.','.'), COALESCE(p.last_name,''), COALESCE(p.suffix,'')),
                '\s+',' ','g')) AS full_name,
            fu.family_num,
            pps.lmp,
            pps.edc AS edd,
            ps.person_status_name AS person_status
            FROM target t
            JOIN public.person p ON p.person_id = t.person_id
            LEFT JOIN public.person_status ps ON ps.person_status_id = p.person_status_id
            LEFT JOIN public.family_unit fu ON fu.family_head_id = p.person_id
            LEFT JOIN latest_visit lv ON lv.maternal_record_id = t.maternal_record_id
            LEFT JOIN public.present_pregnancy_status pps ON pps.anc_visit_id = lv.anc_visit_id
            ORDER BY full_name;"""
        params = (person_id, maternal_record_id)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_all_most_recent_records(self) -> list[dict] | None:
        sql = """WITH latest AS (
            SELECT DISTINCT ON (person_id)
                maternal_record_id,
                person_id,
                created_at
            FROM public.maternal_health_record
            ORDER BY person_id, created_at DESC, maternal_record_id DESC
        )
        SELECT
            p.person_id,
            TRIM(
                REGEXP_REPLACE(
                    CONCAT_WS(' ',
                        COALESCE(p.first_name, ''),
                        NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                        COALESCE(p.last_name, ''),
                        COALESCE(p.suffix, '')
                    ),
                    '\s+', ' ', 'g'
                )
            ) AS full_name,
            fu.family_num,
            CONCAT_WS(', ',
                NULLIF(a.street, ''),
                NULLIF(ps.purok_sitio_name, ''),
                CASE WHEN COALESCE(a.barangay, '') <> '' THEN 'Brgy ' || a.barangay ELSE NULL END,
                NULLIF(a.city, '')
            ) AS full_address,
            l.created_at::date AS record_date
        FROM latest AS l
        JOIN public.person AS p
            ON p.person_id = l.person_id
        LEFT JOIN public.family_unit AS fu
            ON fu.family_id = (
                SELECT family_id
                FROM public.maternal_health_record m2
                WHERE m2.maternal_record_id = l.maternal_record_id
            )
        LEFT JOIN public.addresss AS a
            ON a.address_id = p.address_id
        LEFT JOIN public.purok_sitio AS ps
            ON ps.purok_sitio_id = a.purok_sitio_id
        ORDER BY record_date ASC, p.person_id ASC;
        """
        rows = self.ctx.execute_query_to_dict(sql)

        return rows if rows else None
