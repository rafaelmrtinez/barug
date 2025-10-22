from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException
import logging

logger = logging.getLogger(__name__)


class MaternalHealthRecordRepository:

    def __init__(self, ctx: ConnectionAdapter):
        self.ctx = ctx

    def insert_maternal_health_record(self, staff_id, person_id, husband_id, weight, height, bmi_status_id, is_transferred):
        sql = """SELECT * FROM create_maternal_health_record_bhw(%s::INTEGER, %s::INTEGER, %s::INTEGER, %s::DECIMAL, %s::DECIMAL, %s::INTEGER, %s::BOOLEAN);"""
        params = (staff_id, person_id, husband_id, weight,
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

    def fetch_maternal_checklist_by_mhr_id(self, maternal_record_id: int):
        sql = """WITH latest_visit AS (
            SELECT v.anc_visit_id, v.visit_no, v.visit_date
            FROM public.maternal_anc_visit v
            WHERE v.maternal_record_id = %s
            ORDER BY v.visit_date DESC, v.anc_visit_id DESC
            LIMIT 1
            )
            SELECT
            lv.anc_visit_id,
            lv.visit_no,
            lv.visit_date::date AS visit_date,
            mc.maternal_checklist_id,
            mc.checklist_item_id,
            ci.checklist_name
            FROM latest_visit lv
            LEFT JOIN public.maternal_checklist mc
            ON mc.anc_visit_id = lv.anc_visit_id
            LEFT JOIN public.checklist_item ci
            ON ci.checklist_item_id = mc.checklist_item_id
            ORDER BY ci.checklist_name NULLS LAST;"""
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
        sql = """-- $1 := maternal_record_id
            WITH tt_type_map AS (
            -- If you have a tt_type lookup, replace this with a SELECT from that table.
            SELECT 1 AS tt_type_id, 1 AS dose_order, 'TT1' AS dose_label UNION ALL
            SELECT 2, 2, 'TT2' UNION ALL
            SELECT 3, 3, 'TT3' UNION ALL
            SELECT 4, 4, 'TT4' UNION ALL
            SELECT 5, 5, 'TT5'
            ),
            per_type AS (
            -- keep earliest date per type for this maternal record
            SELECT
                r.maternal_record_id,
                r.tt_type_id,
                MIN(r.date_given)::date AS date_given
            FROM public.tt_vaccine_record r
            WHERE r.maternal_record_id = %s
            GROUP BY r.maternal_record_id, r.tt_type_id
            ),
            ordered AS (
            SELECT
                p.maternal_record_id,
                m.dose_order,
                m.dose_label,
                p.date_given
            FROM per_type p
            JOIN tt_type_map m
                ON m.tt_type_id = p.tt_type_id
            )
            SELECT
            maternal_record_id,
            dose_label,                     -- 'TT1'...'TT5'
            date_given,                     -- date given for that dose
            LEAST(ROW_NUMBER() OVER (ORDER BY dose_order), 6) AS fim_level,   -- 1..6
            CONCAT('FIM-', LEAST(ROW_NUMBER() OVER (ORDER BY dose_order), 6)) AS fim_label
            FROM ordered
            ORDER BY dose_order;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows

    def fetch_person_id_by_maternal_record_id(self, maternal_record_id: int):
        sql = """SELECT person_id
            FROM public.maternal_health_record
            WHERE maternal_record_id = %s
            LIMIT 1;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0]['person_id'] if rows else None

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

    def fetch_obstetric_history_by_mhr_id(self, maternal_record_id: int):
        sql = """SELECT
            COALESCE(oh.num_children_born_alive, 0)      AS num_children_born_alive,
            COALESCE(oh.num_children_living, 0)          AS num_children_living,
            COALESCE(oh.num_abortion, 0)                 AS num_abortion,
            COALESCE(oh.num_stillbirth, 0)               AS num_stillbirth_or_fetal_death,
            COALESCE(oh.num_large_babies, 0)             AS num_large_babies,
            COALESCE(oh.has_diabetes, false)             AS has_diabetes,
            mh.previous_hospitalization,
            mh.previous_preg_complication
            FROM public.maternal_health_record m
            LEFT JOIN public.obstetric_history oh
            ON oh.maternal_record_id = m.maternal_record_id
            LEFT JOIN public.medical_history mh
            ON mh.maternal_record_id = m.maternal_record_id
            WHERE m.maternal_record_id = %s
            LIMIT 1;"""
        params = (maternal_record_id,)
        rows = self.ctx.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_all_mhr_form_basic_info_by_mhr_id(self, maternal_record_id: int):
        sql = """SELECT
            fu.family_num                                             AS family_number,
            /* Mother's full name: First M. Last Suffix */
            TRIM(
                REGEXP_REPLACE(
                CONCAT_WS(' ',
                    COALESCE(pm.first_name, ''),
                    NULLIF(LEFT(COALESCE(pm.middle_name, ''), 1) || '.', '.'),
                    COALESCE(pm.last_name, ''),
                    COALESCE(pm.suffix, '')
                ),
                '\s+', ' ', 'g'
                )
            )                                                         AS full_name,
            pm.birthdate::date                                        AS date_of_birth,
            /* Age: prefer stored pm.age; else compute whole years from birthdate */
            COALESCE(
                pm.age,
                EXTRACT(YEAR FROM age(current_date, pm.birthdate))::int
            )                                                         AS age,
            /* Complete address: "Street, Purok/Sitio, Brgy X, City" */
            CONCAT_WS(', ',
                NULLIF(a.street, ''),
                NULLIF(ps.purok_sitio_name, ''),
                CASE WHEN COALESCE(a.barangay, '') <> '' THEN 'Brgy ' || a.barangay ELSE NULL END,
                NULLIF(a.city, '')
            )                                                         AS address,
            /* Husband's full name (if set on the MHR) */
            TRIM(
                REGEXP_REPLACE(
                CONCAT_WS(' ',
                    COALESCE(ph.first_name, ''),
                    NULLIF(LEFT(COALESCE(ph.middle_name, ''), 1) || '.', '.'),
                    COALESCE(ph.last_name, ''),
                    COALESCE(ph.suffix, '')
                ),
                '\s+', ' ', 'g'
                )
            )                                                         AS husband_full_name,
            pm.occupation                                             AS occupation
            FROM public.maternal_health_record AS m
            JOIN public.person AS pm
            ON pm.person_id = m.person_id               -- mother
            LEFT JOIN public.person AS ph
            ON ph.person_id = m.husband_id              -- husband (optional)
            LEFT JOIN public.family_unit AS fu
            ON fu.family_head_id = pm.person_id         -- assumes mother is family head
            LEFT JOIN public.addresss AS a
            ON a.address_id = pm.address_id
            LEFT JOIN public.purok_sitio AS ps
            ON ps.purok_sitio_id = a.purok_sitio_id
            WHERE m.maternal_record_id = %s
            LIMIT 1;"""
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
