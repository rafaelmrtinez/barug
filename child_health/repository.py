from child_health.exception.child_health_record_exception import ChildHealthRecordException
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

import logging

logger = logging.getLogger(__name__)


class ChildHealthRecordRepository:
    def __init__(self, ctx: ConnectionAdapter):
        self.ctx = ctx
        logger.info("ChildHealthRecordRepository initialized")
        
    def fetch_new_born_screening_date_by_chr_id(self, chr_id: int) -> dict | None:
        sql="""SELECT
            s.referred_newborn_screening_date
            FROM
            feeding_type_nwbrn_scrnng s
            JOIN child_visit v ON v.visit_id = s.visit_id
            WHERE
            v.child_record_id = %s
            ORDER BY feeding_type_nwbrn_scrnng_id DESC
            LIMIT 1;
        """
        params = [chr_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result
        
    def insert_new_born_screening_date(self, p_child_record_id, p_assessed_by_id, p_referred_nbs_date):
        sql="""SELECT * FROM add_referred_newborn_screening_date(%s, %s, %s);"""
        params = [p_child_record_id, p_assessed_by_id, p_referred_nbs_date]
        try:
            result = self.ctx.execute_query(sql, params)
            if not result:
                return None
            return result
        except QueryExecutionException as e:
            logger.error(f"Error inserting new born screening date: {e}")
            if ChildHealthRecordException.is_child_health_record_exception(e.code):
                raise ChildHealthRecordException(e.message) from e
            raise e

    def fetch_immunization_dates_matrix_by_chr_id(self, chr_id: int) -> dict | None:
        print(f"Fetching immunization dates matrix for chr_id: {chr_id}")
        sql="""-- Repository SQL: pivot immunization dates per type for a child record
            -- params: $1 = child_record_id
            WITH src AS (
            SELECT
                ci.child_record_id,
                ci.immunization_type_id,
                ci.immunization_stage_given_id,
                ci.date_given,
                it.immunization_type_name
            FROM child_immunization ci
            JOIN immunization_type it USING (immunization_type_id)
            WHERE ci.child_record_id = %s
            )
            SELECT
            immunization_type_id,
            immunization_type_name,
            -- pick most recent per stage to ensure a single value
            MAX(date_given) FILTER (WHERE immunization_stage_given_id = 1) AS date_24hr,
            MAX(date_given) FILTER (WHERE immunization_stage_given_id = 2) AS date_1st,
            MAX(date_given) FILTER (WHERE immunization_stage_given_id = 3) AS date_2nd,
            MAX(date_given) FILTER (WHERE immunization_stage_given_id = 4) AS date_3rd
            FROM src
            GROUP BY immunization_type_id, immunization_type_name
            ORDER BY immunization_type_id;
            """
        params = [chr_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result

    def insert_child_immunizations(self, p_child_record_id, p_assessed_by_id, p_immunization_type_id, p_immunization_stage_given_id, p_date_given):
        sql = """SELECT * FROM add_child_immunization(%s, %s, %s, %s, %s);"""
        params = [
            p_child_record_id, p_assessed_by_id,
            p_immunization_type_id, p_immunization_stage_given_id,
            p_date_given]
        try:
            result = self.ctx.execute_query(sql, params)
            if not result:
                return None
            return result
        except QueryExecutionException as e:
            logger.error(f"Error inserting child immunization: {e}")
            if ChildHealthRecordException.is_child_health_record_exception(e.code):
                raise ChildHealthRecordException(e.message) from e
            raise e
        
    def fetch_child_details_bf_display_by_chr_id(self, chr_id: int) -> dict | None:
        sql="""WITH checks AS (
            SELECT
                cbc.bbf_check_id,
                cbc.check_date,
                cbc.child_record_id,
                cbc.visit_id
            FROM child_breastfeeding_check AS cbc
            WHERE cbc.child_record_id = %s
            ORDER BY
                cbc.check_date DESC NULLS LAST,
                cbc.visit_id  DESC,
                cbc.bbf_check_id DESC
            ),
            latest_visit AS (
            SELECT ch.visit_id
            FROM checks ch
            ORDER BY
                ch.check_date DESC NULLS LAST,
                ch.visit_id  DESC,
                ch.bbf_check_id DESC
            LIMIT 1
            ),
            latest_feeding_type AS (
            SELECT
                ftns.feeding_type_nwbrn_scrnng_id,
                ftns.visit_id,
                ftns.feeding_type_id,
                ft.feeding_type_name,
                ftns.referred_newborn_screening_date
            FROM feeding_type_nwbrn_scrnng AS ftns
            LEFT JOIN feeding_type AS ft
                ON ft.feeding_type_id = ftns.feeding_type_id
            WHERE ftns.visit_id = (SELECT visit_id FROM latest_visit)
            )
            SELECT
            ch.bbf_check_id,
            ch.check_date,
            ch.child_record_id,
            ch.visit_id,

            -- Latest feeding type (same for all rows, based on latest visit_id)
            lft.feeding_type_nwbrn_scrnng_id,
            lft.visit_id                 AS latest_visit_id,
            lft.feeding_type_id,
            lft.feeding_type_name,
            lft.referred_newborn_screening_date

            FROM checks ch
            LEFT JOIN latest_feeding_type lft ON TRUE
            ORDER BY
            ch.check_date DESC NULLS LAST,
            ch.visit_id  DESC,
            ch.bbf_check_id DESC;
        """
        params = [chr_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result

    # def insert_bf_check(
    #         self, p_child_record_id, p_visit_no,
    #         p_visit_date, p_assessed_by_id, p_feeding_type_id,
    #         p_referred_newborn_screening_date, p_performer_id, p_user_type_id,
    #         p_subsystem, p_log_details):
    #     sql = """SELECT * FROM set_bf_check_and_newborn_screening(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"""
    #     params = [
    #         p_child_record_id, p_visit_no, p_visit_date, p_assessed_by_id,
    #         p_feeding_type_id, p_referred_newborn_screening_date,
    #         p_performer_id, p_user_type_id, p_subsystem, p_log_details]
    #     try:
    #         result = self.ctx.execute_query(sql, params)
    #         if not result:
    #             return None
    #         return result[0]
    #     except QueryExecutionException as e:
    #         logger.error(f"Error inserting BF check: {e}")
    #         if ChildHealthRecordException.is_child_health_record_exception(e.code):
    #             raise ChildHealthRecordException(e.message) from e
    #         raise e

    def insert_bf_check(self, p_child_record_id, p_assessed_by_id, p_feeding_type_id, p_check_date):
        sql = """SELECT * FROM set_feeding_and_add_bf_check(%s, %s, %s, %s);"""
        params = [
            p_child_record_id, p_assessed_by_id,
            p_feeding_type_id, p_check_date]
        try:
            result = self.ctx.execute_query(sql, params)
            if not result:
                return None
            return result[0]
        except QueryExecutionException as e:
            logger.error(f"Error inserting feeding type: {e}")
            if ChildHealthRecordException.is_child_health_record_exception(e.code):
                raise ChildHealthRecordException(e.message) from e
            raise e

    def fetch_child_health_record_info_by_chr_id(self, chr_id: int) -> dict | None:
        sql = """/* Input: %s = child_record_id */
            SELECT
            c.child_record_id,

            /* Family / UFC */
            fu.family_num,
            fu.ufc_num,

            /* Child */
            (pc.first_name
                || ' ' || COALESCE(SUBSTRING(pc.middle_name FROM 1 FOR 1) || '. ', '')
                || pc.last_name
                || COALESCE(' ' || pc.suffix, '')
            ) AS child_full_name,
            sx.sex_name                       AS child_gender,
            c.birth_order                     AS child_birth_order,
            pc.birthdate                      AS date_of_birth,
            dpt.delivery_place_type_name      AS place_of_delivery,

            /* Mother */
            (pm.first_name
                || ' ' || COALESCE(SUBSTRING(pm.middle_name FROM 1 FOR 1) || '. ', '')
                || pm.last_name
                || COALESCE(' ' || pm.suffix, '')
            ) AS mother_full_name,
            CASE WHEN pm.birthdate IS NOT NULL
                THEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, pm.birthdate))::INT
                ELSE NULL
            END                               AS mothers_age,
            pm.occupation                     AS mothers_occupation,

            /* Father */
            (pf.first_name
                || ' ' || COALESCE(SUBSTRING(pf.middle_name FROM 1 FOR 1) || '. ', '')
                || pf.last_name
                || COALESCE(' ' || pf.suffix, '')
            ) AS father_full_name,
            CASE WHEN pf.birthdate IS NOT NULL
                THEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, pf.birthdate))::INT
                ELSE NULL
            END                               AS fathers_age,
            pf.occupation                     AS fathers_occupation,

            /* Child complete address */
            TRIM(BOTH ', ' FROM CONCAT_WS(', ',
                NULLIF(a.street, ''),
                NULLIF(ps.purok_sitio_name, ''),
                NULLIF(a.barangay, ''),
                NULLIF(a.city, '')
            ))                                 AS child_complete_address,

            /* When CHR was created (optional) */
            c.created_at                       AS record_created_at

            FROM child_health_record       AS c
            LEFT JOIN family_unit          AS fu ON fu.family_id = c.family_id
            LEFT JOIN person               AS pc ON pc.person_id = c.person_id
            LEFT JOIN sex                  AS sx ON sx.sex_id    = pc.sex_id
            LEFT JOIN delivery_place_type  AS dpt ON dpt.delivery_place_type_id = c.delivery_place_type_id
            LEFT JOIN person               AS pm ON pm.person_id = c.mother_id
            LEFT JOIN person               AS pf ON pf.person_id = c.father_id
            LEFT JOIN addresss             AS a  ON a.address_id = pc.address_id
            LEFT JOIN purok_sitio          AS ps ON ps.purok_sitio_id = a.purok_sitio_id
            WHERE c.child_record_id = 10;   -- supply the specific child_record_id"""

        params = [chr_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result

    def fetch_all_basic_chr_record(self):
        sql = """SELECT
            c.child_record_id,
            c.person_id                                  AS child_id,
            /* Child full name */
            (pc.first_name
                || ' ' || COALESCE(SUBSTRING(pc.middle_name FROM 1 FOR 1) || '. ', '')
                || pc.last_name)                          AS child_full_name,

            /* Mother */
            c.mother_id,
            (pm.first_name
                || ' ' || COALESCE(SUBSTRING(pm.middle_name FROM 1 FOR 1) || '. ', '')
                || pm.last_name)                          AS mother_full_name,

            /* Father */
            c.father_id,
            (pf.first_name
                || ' ' || COALESCE(SUBSTRING(pf.middle_name FROM 1 FOR 1) || '. ', '')
                || pf.last_name)                          AS father_full_name,

            /* Family number from CHR's family_id */
            fu.family_num,

            /* When the CHR was created */
            c.created_at                                 AS record_created_at

            FROM child_health_record AS c
            LEFT JOIN person       AS pc ON pc.person_id = c.person_id
            LEFT JOIN person       AS pm ON pm.person_id = c.mother_id
            LEFT JOIN person       AS pf ON pf.person_id = c.father_id
            LEFT JOIN family_unit  AS fu ON fu.family_id = c.family_id
            ORDER BY c.created_at DESC, c.child_record_id DESC;
        """
        return self.ctx.execute_query_to_dict(sql, [])

    def insert_chr_record(self, p_staff_id, p_person_id, p_birth_order, p_delivery_place_type_id):
        try:
            sql = """SELECT * FROM create_child_health_record(%s, %s, %s, %s);"""
            params = [p_staff_id, p_person_id,
                      p_birth_order, p_delivery_place_type_id]
            result = self.ctx.execute_query(sql, params)
            if not result:
                return None
            return result[0]
        except QueryExecutionException as e:
            logger.error(f"Error inserting child health record: {e}")
            if ChildHealthRecordException.is_child_health_record_exception(e.code):
                raise ChildHealthRecordException(e.message) from e
            raise e
        except Exception as e:
            logger.error(
                f"Unexpected error inserting child health record: {e}")
            raise e

    def fetch_person_and_house_basic_details_by_id(self, person_id: int) -> dict | None:
        sql = """/* Input: :person_id (the child’s person_id) */
            WITH base AS (
            SELECT p.person_id,
                    p.birthdate,
                    p.sex_id,
                    f.family_num,
                    f.ufc_num
            FROM person p
            LEFT JOIN family_unit f
                    ON f.family_head_id = p.person_id
            WHERE p.person_id = %s
            )
            SELECT
            b.family_num,
            b.ufc_num,
            s.sex_name                                 AS sex,
            b.birthdate                                 AS date_of_birth,

            /* Mother */
            mom.person_id                               AS mother_id,
            (mom.first_name
                || ' ' || COALESCE(SUBSTRING(mom.middle_name FROM 1 FOR 1) || '. ', '')
                || mom.last_name)                        AS mother_full_name,
            mom.occupation                              AS mother_occupation,
            CASE WHEN mom.birthdate IS NOT NULL
                THEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, mom.birthdate))::int
                ELSE NULL
            END                                         AS mother_age_years,

            /* Father */
            dad.person_id                               AS father_id,
            (dad.first_name
                || ' ' || COALESCE(SUBSTRING(dad.middle_name FROM 1 FOR 1) || '. ', '')
                || dad.last_name)                        AS father_full_name,
            dad.occupation                              AS father_occupation,
            CASE WHEN dad.birthdate IS NOT NULL
                THEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, dad.birthdate))::int
                ELSE NULL
            END                                         AS father_age_years

            FROM base b
            LEFT JOIN sex s ON s.sex_id = b.sex_id

            /* Mother: prefer active link, else most recent historical; relationship_id = 4 */
            LEFT JOIN LATERAL (
            SELECT p2.*
            FROM person_kinship pk
            JOIN person p2 ON p2.person_id = pk.dst_person_id
            WHERE pk.src_person_id  = b.person_id
                AND pk.relationship_id = 4
            ORDER BY
                (pk.is_active IS TRUE AND pk.end_date IS NULL) DESC,  -- prefer active
                COALESCE(pk.start_date, pk.added_at) DESC,
                pk.kinship_id DESC
            LIMIT 1
            ) mom ON TRUE

            /* Father: prefer active link, else most recent historical; relationship_id = 5 */
            LEFT JOIN LATERAL (
            SELECT p3.*
            FROM person_kinship pk
            JOIN person p3 ON p3.person_id = pk.dst_person_id
            WHERE pk.src_person_id  = b.person_id
                AND pk.relationship_id = 5
            ORDER BY
                (pk.is_active IS TRUE AND pk.end_date IS NULL) DESC,  -- prefer active
                COALESCE(pk.start_date, pk.added_at) DESC,
                pk.kinship_id DESC
            LIMIT 1
            ) dad ON TRUE;
        """
        params = [person_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        print("Person and House Basic Details:", result)
        return result

    def find_person_basic_details_by_id(self, person_id: int) -> dict | None:
        sql = """-- Fetch age (computed) and occupation for a given person_id
            SELECT
            p.person_id,
            -- Return NULL if birthdate is NULL or in the future; else compute exact years
            CASE
                WHEN p.birthdate IS NULL OR p.birthdate > CURRENT_DATE
                THEN NULL
                ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birthdate))::int
            END AS age_years,
            p.occupation
            FROM public."person" AS p
            WHERE p.person_id = %s;  -- supply person_id here
        """
        params = [person_id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result

    def match_person_by_key(self, key: str):
        key = (key or "").strip()
        if len(key) < 2:
            return []

        like = f"%{key}%"
        sql = """
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
            '\s+',
            ' ',
            'g'
            )
        ) AS full_name,
        -- Build a clean full address: "Street, Purok/Sitio, Brgy {barangay}, {city}"
        CONCAT_WS(', ',
            NULLIF(a.street, ''),
            NULLIF(ps.purok_sitio_name, ''),
            CASE WHEN COALESCE(a.barangay, '') <> '' THEN 'Brgy ' || a.barangay ELSE NULL END,
            NULLIF(a.city, '')
        ) AS address
        FROM public.person AS p
        LEFT JOIN public.addresss AS a
        ON a.address_id = p.address_id
        LEFT JOIN public.purok_sitio AS ps
        ON ps.purok_sitio_id = a.purok_sitio_id
        WHERE
            p.first_name ILIKE %s
        OR p.middle_name ILIKE %s
        OR p.last_name  ILIKE %s
        OR (p.first_name || ' ' || p.last_name) ILIKE %s
        OR (p.last_name  || ', ' || p.first_name) ILIKE %s
        ORDER BY COALESCE(p.last_name, '') ASC, COALESCE(p.first_name, '') ASC
        LIMIT 25;
        """
        params = (like, like, like, like, like)
        result = self.ctx.execute_query_to_dict(sql, params)

        if not result:
            return []

        return result

    def fetch_child_monitoring_logs(self, child_record_id: int) -> list[dict]:
        sql = """
        SELECT
        cml.child_monitoring_id,
        cml.check_date::date AS check_date,
        cml.age,
        cml.weight,
        cml.temperature,
        cml.height,
        cml.findings,
        cml.notes,
        cml.visit_id
        FROM public.child_monitoring_log cml
        WHERE cml.child_record_id = %s
        ORDER BY cml.check_date DESC NULLS LAST, cml.child_monitoring_id DESC;
        """
        return self.ctx.execute_query_to_dict(sql, [child_record_id]) or []

    def fetch_child_screening_package(self, child_record_id: int) -> dict | None:
        sql = """
        WITH latest_screen AS (
            SELECT DISTINCT ON (csa.child_record_id)
                csa.child_record_id,
                csa.screening_id,
                csa.date_assessed::date               AS date_assessed,
                csa.birth_weight,
                csa.anemic_seen_date::date            AS anemic_2_59_seen_date,
                csa.anemic_given_iron_date::date      AS anemic_2_59_given_iron_date,
                csa.iron_seen_2_6_mos_date::date      AS seen_2_6_mos_date,
                csa.iron_given_2_6_mos_date::date     AS given_2_6_mos_date
            FROM public.child_screening_assessment csa
            WHERE csa.child_record_id = %s
            ORDER BY csa.child_record_id, csa.date_assessed DESC NULLS LAST, csa.screening_id DESC
        ),
        iron AS (
            SELECT
                cis.child_record_id,
                MIN(cis.date_started)::date   AS iron_date_started,
                MAX(cis.date_completed)::date AS iron_date_completed
            FROM public.child_iron_supplement_record cis
            WHERE cis.child_record_id = %s
            GROUP BY cis.child_record_id
        ),
        vit AS (
            SELECT
                vag.child_record_id,
                MIN(CASE WHEN vag.vit_stage_id = 1 THEN vag.date_given::date END) AS vit_a_given_1,
                MIN(CASE WHEN vag.vit_stage_id = 2 THEN vag.date_given::date END) AS vit_a_given_2,
                MIN(CASE WHEN vag.vit_stage_id = 3 THEN vag.date_given::date END) AS vit_a_given_3
            FROM public.vitamin_a_given vag
            WHERE vag.child_record_id = %s
            GROUP BY vag.child_record_id
        )
        SELECT
            COALESCE(ls.child_record_id, i.child_record_id, v.child_record_id) AS child_record_id,
            ls.date_assessed,
            ls.birth_weight,
            ls.anemic_2_59_seen_date,
            ls.anemic_2_59_given_iron_date,
            ls.seen_2_6_mos_date,
            ls.given_2_6_mos_date,
            i.iron_date_started,
            i.iron_date_completed,
            v.vit_a_given_1,
            v.vit_a_given_2,
            v.vit_a_given_3
        FROM latest_screen ls
        FULL OUTER JOIN iron i ON i.child_record_id = ls.child_record_id
        FULL OUTER JOIN vit  v ON v.child_record_id  = COALESCE(ls.child_record_id, i.child_record_id)
        LIMIT 1;
        """
        rows = self.ctx.execute_query_to_dict(
            sql, [child_record_id, child_record_id, child_record_id])
        return rows[0] if rows else None

    def fetch_all_child_immunizations_by_chr_id(self, id: int) -> dict | None:
        sql = """WITH rows AS (
            SELECT
                it.immunization_type_name  AS type_name,
                sg.immunization_stage_name AS stage_name,
                ci.date_given::date        AS date_given
            FROM public.child_immunization           AS ci
            JOIN public.immunization_type            AS it ON it.immunization_type_id = ci.immunization_type_id
            JOIN public.immunization_stage_given     AS sg ON sg.immunization_stage_given_id = ci.immunization_stage_given_id
            WHERE ci.child_record_id = %s
            )
            SELECT type_name, stage_name, MAX(date_given) AS date_given
            FROM rows
            GROUP BY type_name, stage_name"""
        params = [id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result

    def fetch_child_record_id_by_person_id(self, id: int) -> int | None:
        sql = """SELECT child_record_id FROM child_health_record WHERE person_id = %s;"""
        params = [id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result[0]['child_record_id']

    def fetch_all_feeding_check_dates_by_person_id(self, id: int) -> list[dict]:
        sql = """WITH target AS (
            SELECT chr.child_record_id
            FROM public.child_health_record AS chr
            WHERE chr.person_id = %s
            ORDER BY chr.created_at DESC, chr.child_record_id DESC
            LIMIT 1
            )
            SELECT
            cbc.bbf_check_id,
            cbc.check_date,
            cbc.visit_id,
            cv.visit_no,
            cv.visit_date::date AS visit_date
            FROM public.child_breastfeeding_check AS cbc
            JOIN target t
            ON t.child_record_id = cbc.child_record_id
            LEFT JOIN public.child_visit AS cv
            ON cv.visit_id = cbc.visit_id
            ORDER BY
            cbc.check_date ASC,
            cv.visit_date ASC NULLS LAST,
            cbc.bbf_check_id ASC
            LIMIT 5;"""
        params = [id]
        return self.ctx.execute_query_to_dict(sql, params)

    def fetch_all_feeding_type(self) -> list[dict]:
        sql = """SELECT feeding_type_id, feeding_type_name FROM public.feeding_type;"""
        return self.ctx.execute_query_to_dict(sql, [])

    def fetch_child_newborn_screening_by_person_id(self, id: int) -> dict | None:
        sql = """WITH target AS (
            -- Resolve the most recent child record for this person
            SELECT chr.child_record_id
            FROM public.child_health_record AS chr
            WHERE chr.person_id = %s
            ORDER BY chr.created_at DESC, chr.child_record_id DESC
            LIMIT 1
            ),
            feeding_visits AS (
            -- Only visits that actually have a feeding entry
            SELECT
                cv.child_record_id,
                cv.visit_id,
                cv.visit_no,
                cv.visit_date::date                             AS visit_date,
                cv.created_at                                   AS visit_created_at,
                ftns.feeding_type_id,
                ftns.referred_newborn_screening_date::date     AS referred_nbs_date
            FROM public.child_visit AS cv
            JOIN public.feeding_type_nwbrn_scrnng AS ftns
                ON ftns.visit_id = cv.visit_id
            JOIN target t
                ON t.child_record_id = cv.child_record_id
            ),
            latest AS (
            -- Pick the single most recent feeding entry for this child
            SELECT DISTINCT ON (fv.child_record_id)
                    fv.child_record_id,
                    fv.visit_id,
                    fv.visit_no,
                    fv.visit_date,
                    fv.visit_created_at,
                    fv.feeding_type_id,
                    fv.referred_nbs_date
            FROM feeding_visits fv
            ORDER BY
                fv.child_record_id,
                fv.visit_date DESC NULLS LAST,
                fv.visit_created_at DESC NULLS LAST,
                fv.visit_id DESC
            )
            SELECT
            l.child_record_id,
            l.visit_id,
            l.visit_no,
            l.visit_date,
            l.referred_nbs_date,
            l.feeding_type_id,
            ft.feeding_type_name
            FROM latest l
            LEFT JOIN public.feeding_type ft
            ON ft.feeding_type_id = l.feeding_type_id;"""
        params = [id]
        result = self.ctx.execute_query_to_dict(sql, params)
        if not result:
            return None
        return result[0]

    def fetch_child_basic_information_by_person_id(self, id: int) -> dict | None:
        raw = """
            SELECT 
            family_unit.family_num,
            family_unit.ufc_num,
            CONCAT(CHILD.first_name, ' ', COALESCE(CHILD.middle_name, ''), ' ', CHILD.last_name, ' ', COALESCE(CHILD.suffix, '')) AS CHILD,
            SEX.sex_name,
            CHR.birth_order,
            CHILD.birthdate AS DATE_OF_BIRTH,
            delivery_place_type.delivery_place_type_name AS PLACE_OF_DELIVERY,
            CONCAT(MOTHER.first_name, ' ', COALESCE(MOTHER.middle_name, ''), ' ', MOTHER.last_name, ' ', COALESCE(MOTHER.suffix, '')) AS MOTHER_NAME,
            COALESCE(MOTHER.occupation, 'N/A') AS MOTHER_OCCUPATION,
            MOTHER.age AS MOTHER_AGE,
            CONCAT(FATHER.first_name, ' ', COALESCE(FATHER.middle_name, ''), ' ', FATHER.last_name, ' ', COALESCE(FATHER.suffix, '')) AS FATHER_NAME,
            COALESCE(FATHER.occupation, 'N/A') AS FATHER_OCCUPATION,
            FATHER.age AS FATHER_AGE,
            CONCAT(
                household_info.house_number, ', ', purok_sitio.purok_sitio_name, ', ',
                addresss.street, ', ', addresss.barangay, ', ', addresss.city, ', 6000'
            ) AS ADDRESS
            FROM child_health_record AS CHR
            INNER JOIN person AS CHILD ON CHILD.person_id = CHR.person_id
            LEFT JOIN person AS MOTHER ON MOTHER.person_id = CHR.mother_id
            LEFT JOIN person AS FATHER ON FATHER.person_id = CHR.father_id
            INNER JOIN family_unit ON family_unit.family_id = CHR.family_id
            INNER JOIN addresss ON addresss.address_id = CHILD.address_id
            INNER JOIN purok_sitio ON purok_sitio.purok_sitio_id = addresss.purok_sitio_id
            INNER JOIN household_info ON household_info.household_id = family_unit.household_id
            INNER JOIN sex ON sex.sex_id = CHILD.sex_id
            INNER JOIN delivery_place_type ON delivery_place_type.delivery_place_type_id = CHR.delivery_place_type_id
            WHERE CHILD.person_id = %s;
        """
        params = [id]
        result = self.ctx.execute_query_to_dict(raw, params)

        if not result:
            return None
        return result[0]

    def fetch_all_basic_records(self):
        raw = """
            SELECT 
            CHILD.person_id AS CHILD_ID,
            family_unit.family_num,
            CONCAT(CHILD.first_name, ' ', COALESCE(CHILD.middle_name, ''), ' ', CHILD.last_name, ' ', COALESCE(CHILD.suffix, '')) AS CHILD,
            CONCAT(MOTHER.first_name, ' ', COALESCE(MOTHER.middle_name, ''), ' ', MOTHER.last_name, ' ', COALESCE(MOTHER.suffix, '')) AS MOTHER,
            CONCAT(FATHER.first_name, ' ', COALESCE(FATHER.middle_name, ''), ' ', FATHER.last_name, ' ', COALESCE(FATHER.suffix, '')) AS FATHER,
            CHR.created_at AS DATE_ADDED
            FROM child_health_record AS CHR
            INNER JOIN person AS CHILD
            ON CHILD.person_id = CHR.person_id
            INNER JOIN person AS MOTHER
            ON MOTHER.person_id = CHR.person_id
            INNER JOIN person AS FATHER
            ON FATHER.person_id = CHR.person_id
            INNER JOIN family_unit
            ON family_unit.family_id = CHR.family_id
        """
        return self.ctx.execute_query_to_dict(raw, [])
