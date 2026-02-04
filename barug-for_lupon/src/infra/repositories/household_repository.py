from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.household_dto import (
    HouseholdListDTO,
    HouseholdDetailDTO,
    FamilyDTO,
    HouseholdMemberDTO,
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)
from typing import Optional

class HouseholdRepository(IHouseholdRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_household_list(self) -> list[HouseholdListDTO]:
        try:
            sql = """
                SELECT
                  h.household_id,
                  h.household_num,

                  -- Head: First M. Last Suffix
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS household_head,

                  -- Address: "Street, BRGY {barangay}, {city}"
                  TRIM(
                    CONCAT_WS(', ',
                      NULLIF(a.street, ''),
                      CASE WHEN NULLIF(a.barangay,'') IS NOT NULL THEN 'BRGY ' || a.barangay END,
                      NULLIF(a.city, '')
                    )
                  ) AS household_address,

                  COALESCE(ht.house_type_name, '')          AS house_type_name,
                  COALESCE(ho.house_ownership_name, '')     AS household_ownership_name
                FROM public.household_info       AS h
                LEFT JOIN public.person          AS p  ON p.person_id = h.household_head_id
                LEFT JOIN public.addresss        AS a  ON a.address_id = h.address_id
                LEFT JOIN public.house_type      AS ht ON ht.house_type_id = h.house_type_id
                LEFT JOIN public.house_ownership AS ho ON ho.house_ownership_id = h.house_ownership_id
                -- Optional: only active households
                WHERE h.is_active IS TRUE
                ORDER BY h.household_num;
            """

            rows = self._ctx.execute_query_to_dict(sql, [])

            return [HouseholdListDTO(**row) for row in rows]

        except Exception as e:
            raise QueryExecutionException(f"fetch_household_list failed: {e}") from e
        
    def search_household(self, search: str) -> list[HouseholdListDTO]:
        try:
            sql = """
            WITH base AS (
            SELECT
                h.household_id,
                h.household_num,
                TRIM(
                CONCAT_WS(' ',
                    COALESCE(p.first_name, ''),
                    NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                    COALESCE(p.last_name, ''),
                    COALESCE(p.suffix, '')
                )
                ) AS household_head,
                TRIM(
                COALESCE(a.street,'') ||
                COALESCE(' ' || ps.purok_sitio_name,'') ||
                CASE WHEN COALESCE(a.barangay,'') <> '' THEN
                    (CASE WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL THEN ', ' ELSE '' END)
                    || 'BRGY ' || a.barangay
                ELSE '' END ||
                CASE WHEN COALESCE(a.city,'') <> '' THEN
                    (CASE WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL OR COALESCE(a.barangay,'') <> '' THEN ', ' ELSE '' END)
                    || a.city
                ELSE '' END
                ) AS household_address,
                COALESCE(ht.house_type_name, '')      AS house_type_name,
                COALESCE(ho.house_ownership_name, '') AS household_ownership_name
            FROM public.household_info       AS h
            LEFT JOIN public.person          AS p  ON p.person_id = h.household_head_id
            LEFT JOIN public.addresss        AS a  ON a.address_id = h.address_id
            LEFT JOIN public.purok_sitio     AS ps ON ps.purok_sitio_id = a.purok_sitio_id
            LEFT JOIN public.house_type      AS ht ON ht.house_type_id = h.house_type_id
            LEFT JOIN public.house_ownership AS ho ON ho.house_ownership_id = h.house_ownership_id
            )
            SELECT
            household_id,
            household_num,
            household_head,
            household_address,
            house_type_name,
            household_ownership_name
            FROM base
            WHERE NULLIF(TRIM(%s), '') IS NULL
            OR (
                    household_head    ILIKE '%%' || %s || '%%'
                OR household_address ILIKE '%%' || %s || '%%'
            )
            ORDER BY household_num NULLS LAST;
            """
            key = (search or "").strip()
            rows = self._ctx.execute_query_to_dict(sql, [key, key, key])
            return [HouseholdListDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"search_household failed: {e}", "QRY_SEARCH_HOUSEHOLD") from e
       
    def sort_house_type(self, house_type_id: int) -> list[HouseholdListDTO]:
        try:
            sql = """
            WITH base AS (
            SELECT
                h.household_id,
                h.household_num,

                -- Head: First M. Last Suffix
                TRIM(
                CONCAT_WS(' ',
                    COALESCE(p.first_name, ''),
                    NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                    COALESCE(p.last_name, ''),
                    COALESCE(p.suffix, '')
                )
                ) AS household_head,

                /* Address: street + (purok) + BRGY + city */
                TRIM(
                COALESCE(a.street,'') ||
                COALESCE(' ' || ps.purok_sitio_name,'') ||
                CASE
                    WHEN COALESCE(a.barangay,'') <> '' THEN
                    (CASE WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL THEN ', ' ELSE '' END)
                    || 'BRGY ' || a.barangay
                    ELSE '' END ||
                CASE
                    WHEN COALESCE(a.city,'') <> '' THEN
                    (CASE
                        WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL OR COALESCE(a.barangay,'') <> '' THEN ', '
                        ELSE '' END) || a.city
                    ELSE '' END
                ) AS household_address,

                COALESCE(ht.house_type_name, '')      AS house_type_name,
                COALESCE(ho.house_ownership_name, '') AS household_ownership_name,
                h.house_type_id                        -- keep id for WHERE outside
            FROM public.household_info       AS h
            LEFT JOIN public.person          AS p  ON p.person_id = h.household_head_id
            LEFT JOIN public.addresss        AS a  ON a.address_id = h.address_id
            LEFT JOIN public.purok_sitio     AS ps ON ps.purok_sitio_id = a.purok_sitio_id
            LEFT JOIN public.house_type      AS ht ON ht.house_type_id = h.house_type_id
            LEFT JOIN public.house_ownership AS ho ON ho.house_ownership_id = h.house_ownership_id
            )
            SELECT
            household_id,
            household_num,
            household_head,
            household_address,
            house_type_name,
            household_ownership_name
            FROM base
            WHERE house_type_id = %s
            ORDER BY household_head ASC NULLS LAST, household_num ASC NULLS LAST;
            """
            rows = self._ctx.execute_query_to_dict(sql, [house_type_id])
            return [HouseholdListDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"sort_house_type failed: {e}", "QRY_SORT_HOUSE_TYPE") from e

    def sort_ownership_type(self, ownership_type_id: int) -> list[HouseholdListDTO]:
        try:
            sql = """
            WITH base AS (
            SELECT
                h.household_id,
                h.household_num,

                -- Head: First M. Last Suffix
                TRIM(
                CONCAT_WS(' ',
                    COALESCE(p.first_name, ''),
                    NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                    COALESCE(p.last_name, ''),
                    COALESCE(p.suffix, '')
                )
                ) AS household_head,

                /* Address: street + (purok) + BRGY + city */
                TRIM(
                COALESCE(a.street,'') ||
                COALESCE(' ' || ps.purok_sitio_name,'') ||
                CASE
                    WHEN COALESCE(a.barangay,'') <> '' THEN
                    (CASE WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL THEN ', ' ELSE '' END)
                    || 'BRGY ' || a.barangay
                    ELSE '' END ||
                CASE
                    WHEN COALESCE(a.city,'') <> '' THEN
                    (CASE
                        WHEN COALESCE(a.street,'') <> '' OR ps.purok_sitio_name IS NOT NULL OR COALESCE(a.barangay,'') <> '' THEN ', '
                        ELSE '' END) || a.city
                    ELSE '' END
                ) AS household_address,

                COALESCE(ht.house_type_name, '')      AS house_type_name,
                COALESCE(ho.house_ownership_name, '') AS household_ownership_name,
                h.house_ownership_id                   -- keep id for WHERE outside
            FROM public.household_info       AS h
            LEFT JOIN public.person          AS p  ON p.person_id = h.household_head_id
            LEFT JOIN public.addresss        AS a  ON a.address_id = h.address_id
            LEFT JOIN public.purok_sitio     AS ps ON ps.purok_sitio_id = a.purok_sitio_id
            LEFT JOIN public.house_type      AS ht ON ht.house_type_id = h.house_type_id
            LEFT JOIN public.house_ownership AS ho ON ho.house_ownership_id = h.house_ownership_id
            )
            SELECT
            household_id,
            household_num,
            household_head,
            household_address,
            house_type_name,
            household_ownership_name
            FROM base
            WHERE house_ownership_id = %s
            ORDER BY household_head ASC NULLS LAST, household_num ASC NULLS LAST;
            """
            rows = self._ctx.execute_query_to_dict(sql, [ownership_type_id])
            return [HouseholdListDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"sort_ownership_type failed: {e}", "QRY_SORT_OWNERSHIP") from e

    def fetch_household_pins(
        self,
        *,
        search: str | None = None,
        house_type: int | None = None,
        ownership_type: int | None = None,
    ) -> list[dict]:
        """
        Returns household map pins with optional filters. Mirrors the approach used in BusinessRepository.fetch_business_pins:
          • Filters wired via a params CTE (fixed placeholders)
          • Only rows with address latitude & longitude are returned
          • Search matches head name, street, purok, barangay, city
        """
        try:
            sql = """
                WITH params AS (
                  SELECT
                    %s::int  AS p_house_type,
                    %s::int  AS p_ownership,
                    %s::text AS p_search
                )
                SELECT
                  h.household_id,
                  h.household_num,

                  -- Head: "First M. Last Suffix"
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS household_head,

                  -- Address line for popup
                  TRIM(
                    CONCAT_WS(', ',
                      NULLIF(
                        TRIM(
                          CONCAT(
                            COALESCE(a.street,''),
                            CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> ''
                                 THEN ' ' || ps.purok_sitio_name ELSE '' END
                          )
                        ), ''
                      ),
                      CASE WHEN COALESCE(a.barangay,'') <> '' THEN 'BRGY ' || a.barangay END,
                      NULLIF(a.city,'')
                    )
                  ) AS address_line,

                  -- Display helpers
                  COALESCE(ht.house_type_name, '')      AS house_type_name,
                  COALESCE(ho.house_ownership_name, '') AS ownership_type_name,
                  ps.purok_sitio_name                    AS purok,

                  -- Map coordinates
                  a.latitude::float8  AS lat,
                  a.longitude::float8 AS lng
                FROM public.household_info       AS h
                JOIN public.addresss             AS a  ON a.address_id = h.address_id
                LEFT JOIN public.person          AS p  ON p.person_id = h.household_head_id
                LEFT JOIN public.purok_sitio     AS ps ON ps.purok_sitio_id = a.purok_sitio_id
                LEFT JOIN public.house_type      AS ht ON ht.house_type_id = h.house_type_id
                LEFT JOIN public.house_ownership AS ho ON ho.house_ownership_id = h.house_ownership_id
                CROSS JOIN params pms
                WHERE a.latitude  IS NOT NULL
                  AND a.longitude IS NOT NULL
                  AND h.house_type_id       = COALESCE(pms.p_house_type,  h.house_type_id)
                  AND h.house_ownership_id  = COALESCE(pms.p_ownership,   h.house_ownership_id)
                  AND (
                        COALESCE(pms.p_search,'') = ''
                     OR (
                          TRIM(CONCAT_WS(' ',
                                COALESCE(p.first_name, ''),
                                NULLIF(LEFT(COALESCE(p.middle_name, ''),1) || '.', '.'),
                                COALESCE(p.last_name, ''),
                                COALESCE(p.suffix, '')
                              )) ILIKE '%%' || pms.p_search || '%%'
                        )
                     OR COALESCE(a.street,'')   ILIKE '%%' || pms.p_search || '%%'
                     OR COALESCE(ps.purok_sitio_name,'') ILIKE '%%' || pms.p_search || '%%'
                     OR COALESCE(a.barangay,'') ILIKE '%%' || pms.p_search || '%%'
                     OR COALESCE(a.city,'')     ILIKE '%%' || pms.p_search || '%%'
                  )
                ORDER BY household_head NULLS LAST, household_num;
            """

            params = [
                house_type,          # %s::int  -> p_house_type
                ownership_type,      # %s::int  -> p_ownership
                (search or None),    # %s::text -> p_search
            ]

            return self._ctx.execute_query_to_dict(sql, params) or []

        except Exception as e:
            # keep a code for consistent error handling like you did in BusinessRepository
            raise QueryExecutionException(f"fetch_household_pins failed: {e}", "E_DB")

    def fetch_household_detail(self, household_id: int) -> Optional[HouseholdDetailDTO]:
        """
        Calls the RPC function get_active_household_fam_and_member to retrieve
        household details with families and members.
        """
        try:
            sql = """
                SELECT public.get_active_household_fam_and_member(%s) AS result;
            """
            rows = self._ctx.execute_query_to_dict(sql, [household_id])
            
            if not rows or not rows[0].get('result'):
                return None
            
            result = rows[0]['result']
            household_data = result.get('household')
            families_data = result.get('families', [])
            
            if not household_data:
                return None
            
            # Parse families and members
            families = []
            for family in families_data:
                members_data = family.get('members', [])
                members = [
                    HouseholdMemberDTO(
                        person_id=m.get('person_id'),
                        full_name=m.get('full_name', ''),
                        relationship_to_household_head=m.get('relationship_to_household_head'),
                        age=m.get('age'),
                        sex=m.get('sex')
                    )
                    for m in members_data
                ]
                
                families.append(FamilyDTO(
                    family_id=family.get('family_id'),
                    family_num=family.get('family_num', ''),
                    family_head_name=family.get('family_head_name', ''),
                    household_type=family.get('household_type'),
                    nhts_status=family.get('nhts_status'),
                    indigent_status=family.get('indigent_status'),
                    monthly_income=family.get('monthly_income'),
                    source_of_income=family.get('source_of_income'),
                    members=members
                ))
            
            # Build the HouseholdDetailDTO
            return HouseholdDetailDTO(
                household_id=household_data.get('household_id'),
                household_num=household_data.get('household_num', ''),
                household_head_name=household_data.get('household_head_name', ''),
                house_type=household_data.get('house_type'),
                house_ownership=household_data.get('house_ownership'),
                address=household_data.get('address', ''),
                families=families
            )
            
        except Exception as e:
            raise QueryExecutionException(f"fetch_household_detail failed: {e}", "E_DB") from e

    def fetch_household_history_by_quarter_year(self, quarter: int, year: int) -> list[dict]:
        """
        Calls the RPC function get_household_history_by_quarter_year to retrieve
        household history records for a specific quarter and year.
        """
        try:
            sql = """
                SELECT * FROM public.get_household_history_by_quarter_year(%s, %s);
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"fetch_household_history_by_quarter_year failed: {e}",
                "QRY_HOUSEHOLD_HISTORY"
            ) from e

    def search_household_history(
        self, search: str, quarter: int, year: int
    ) -> list[dict]:
        """
        Search household history by household head name or address.
        Filters by quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_household_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE NULLIF(TRIM(%s), '') IS NULL
               OR householdhead_name ILIKE '%%' || %s || '%%'
               OR street_name ILIKE '%%' || %s || '%%'
               OR purok_sitio_name ILIKE '%%' || %s || '%%'
               OR barangay_name ILIKE '%%' || %s || '%%'
               OR city_name ILIKE '%%' || %s || '%%'
            ORDER BY created_date, household_id;
            """
            key = (search or "").strip()
            rows = self._ctx.execute_query_to_dict(
                sql, [quarter, year, key, key, key, key, key, key]
            )
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"search_household_history failed: {e}",
                "QRY_SEARCH_HOUSEHOLD_HISTORY"
            ) from e

    def sort_household_history_by_house_type(
        self, house_type_id: int, quarter: int, year: int
    ) -> list[dict]:
        """
        Filter household history by house type for a specific quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_household_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE house_type_id = %s
            ORDER BY created_date, household_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, house_type_id])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"sort_household_history_by_house_type failed: {e}",
                "QRY_SORT_HOUSEHOLD_HISTORY_TYPE"
            ) from e

    def sort_household_history_by_ownership(
        self, ownership_id: int, quarter: int, year: int
    ) -> list[dict]:
        """
        Filter household history by ownership type for a specific quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_household_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE house_ownership_id = %s
            ORDER BY created_date, household_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, ownership_id])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"sort_household_history_by_ownership failed: {e}",
                "QRY_SORT_HOUSEHOLD_HISTORY_OWNERSHIP"
            ) from e

    def fetch_household_history_detail(self, household_history_id: int) -> Optional[dict]:
        """
        Calls the RPC function get_household_fam_and_member_history to retrieve
        household history details with families and members.
        """
        try:
            sql = """
                SELECT public.get_household_fam_and_member_history(%s) AS result;
            """
            rows = self._ctx.execute_query_to_dict(sql, [household_history_id])
            
            if not rows or not rows[0].get('result'):
                return None
            
            return rows[0]['result']
            
        except Exception as e:
            raise QueryExecutionException(
                f"fetch_household_history_detail failed: {e}",
                "E_DB"
            ) from e

    def fetch_quarters(self) -> list[dict]:
        """
        Fetch all available quarters from the quarter table.
        """
        try:
            sql = """
                SELECT quarter_id, quarter_name
                FROM public.quarter
                ORDER BY quarter_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"fetch_quarters failed: {e}",
                "QRY_FETCH_QUARTERS"
            ) from e

    def fetch_family_list(self) -> list[dict]:
        """
        Fetch all active families with family head, household info, and status details.
        """
        try:
            sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  
                  -- Family Head: First M. Last Suffix
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  -- Household Number
                  COALESCE(h.household_num, '') AS household_num,
                  
                  -- Statuses
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  
                  -- Income
                  COALESCE(f.source_of_income, '') AS source_of_income,
                  
                  -- IDs for filtering
                  f.household_type_id,
                  f.nhts_status_id,
                  f.indigent_status_id
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                WHERE f.is_active IS TRUE
                ORDER BY f.family_num;
            """
            
            rows = self._ctx.execute_query_to_dict(sql, [])
            return rows or []
            
        except Exception as e:
            raise QueryExecutionException(f"filter_family_by_indigent_status failed: {e}") from e

    # ========================================
    # FAMILY HISTORY METHODS
    # ========================================

    def fetch_family_history_by_quarter_year(self, quarter: int, year: int) -> list[dict]:
        """
        Calls the RPC function get_family_unit_history_by_quarter_year to retrieve
        family history records for a specific quarter and year.
        """
        try:
            sql = """
                SELECT * FROM public.get_family_unit_history_by_quarter_year(%s, %s);
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"fetch_family_history_by_quarter_year failed: {e}",
                "QRY_FAMILY_HISTORY"
            ) from e

    def search_family_history(
        self, search: str, quarter: int, year: int
    ) -> list[dict]:
        """
        Search family history by family head name, family number, or UFC number.
        Filters by quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_family_unit_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE
                LOWER(family_head_name) LIKE LOWER(%s)
                OR LOWER(family_num) LIKE LOWER(%s)
                OR LOWER(ufc_num) LIKE LOWER(%s)
            ORDER BY created_date, family_history_id;
            """
            pattern = f"%{search}%"
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, pattern, pattern, pattern])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"search_family_history failed: {e}",
                "QRY_FAMILY_HISTORY_SEARCH"
            ) from e

    def sort_family_history_by_household_type(
        self, household_type_id: int, quarter: int, year: int
    ) -> list[dict]:
        """
        Filter family history by household type for a specific quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_family_unit_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE household_type_id = %s
            ORDER BY created_date, family_history_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, household_type_id])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"sort_family_history_by_household_type failed: {e}",
                "QRY_FAMILY_HISTORY_FILTER"
            ) from e

    def sort_family_history_by_nhts_status(
        self, nhts_status_id: int, quarter: int, year: int
    ) -> list[dict]:
        """
        Filter family history by NHTS status for a specific quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_family_unit_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE nhts_status_id = %s
            ORDER BY created_date, family_history_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, nhts_status_id])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"sort_family_history_by_nhts_status failed: {e}",
                "QRY_FAMILY_HISTORY_FILTER"
            ) from e

    def sort_family_history_by_indigent_status(
        self, indigent_status_id: int, quarter: int, year: int
    ) -> list[dict]:
        """
        Filter family history by indigent status for a specific quarter and year.
        """
        try:
            sql = """
            WITH base AS (
                SELECT * FROM public.get_family_unit_history_by_quarter_year(%s, %s)
            )
            SELECT *
            FROM base
            WHERE indigent_status_id = %s
            ORDER BY created_date, family_history_id;
            """
            rows = self._ctx.execute_query_to_dict(sql, [quarter, year, indigent_status_id])
            return rows or []
        except Exception as e:
            raise QueryExecutionException(
                f"sort_family_history_by_indigent_status failed: {e}",
                "QRY_FAMILY_HISTORY_FILTER"
            ) from e

    def fetch_family_history_detail(self, family_id: int) -> Optional[dict]:
        """
        Calls the RPC function get_family_unit_history_by_family_id to retrieve
        family history details.
        """
        try:
            sql = """
                SELECT * FROM public.get_family_unit_history_by_family_id(%s);
            """
            rows = self._ctx.execute_query_to_dict(sql, [family_id])
            
            if not rows:
                return None
            
            # Return the first row (should be only one for a specific family_id)
            return rows[0] if rows else None
            
        except Exception as e:
            raise QueryExecutionException(
                f"fetch_family_history_detail failed: {e}",
                "E_DB"
            ) from e

    def search_family(self, search: str) -> list[dict]:
        """
        Search families by family head name, family number, or UFC number.
        """
        try:
            sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  COALESCE(h.household_num, '') AS household_num,
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  COALESCE(f.source_of_income, '') AS source_of_income,
                  
                  f.household_type_id,
                  f.nhts_status_id,
                  f.indigent_status_id
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                WHERE f.is_active IS TRUE
                  AND (
                    NULLIF(TRIM(%s), '') IS NULL
                    OR TRIM(CONCAT_WS(' ',
                         COALESCE(p.first_name, ''),
                         NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                         COALESCE(p.last_name, ''),
                         COALESCE(p.suffix, '')
                       )) ILIKE '%%' || %s || '%%'
                    OR f.family_num ILIKE '%%' || %s || '%%'
                    OR f.ufc_num ILIKE '%%' || %s || '%%'
                  )
                ORDER BY f.family_num;
            """
            
            key = (search or "").strip()
            rows = self._ctx.execute_query_to_dict(sql, [key, key, key, key])
            return rows or []
            
        except Exception as e:
            raise QueryExecutionException(f"search_family failed: {e}", "QRY_SEARCH_FAMILY") from e

    def filter_family_by_household_type(self, household_type_id: int) -> list[dict]:
        """
        Filter families by household type.
        """
        try:
            sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  COALESCE(h.household_num, '') AS household_num,
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  COALESCE(f.source_of_income, '') AS source_of_income,
                  
                  f.household_type_id,
                  f.nhts_status_id,
                  f.indigent_status_id
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                WHERE f.is_active IS TRUE
                  AND f.household_type_id = %s
                ORDER BY f.family_num;
            """
            
            rows = self._ctx.execute_query_to_dict(sql, [household_type_id])
            return rows or []
            
        except Exception as e:
            raise QueryExecutionException(f"filter_family_by_household_type failed: {e}", "QRY_FILTER_FAMILY_HTYPE") from e

    def filter_family_by_nhts_status(self, nhts_status_id: int) -> list[dict]:
        """
        Filter families by NHTS status.
        """
        try:
            sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  COALESCE(h.household_num, '') AS household_num,
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  COALESCE(f.source_of_income, '') AS source_of_income,
                  
                  f.household_type_id,
                  f.nhts_status_id,
                  f.indigent_status_id
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                WHERE f.is_active IS TRUE
                  AND f.nhts_status_id = %s
                ORDER BY f.family_num;
            """
            
            rows = self._ctx.execute_query_to_dict(sql, [nhts_status_id])
            return rows or []
            
        except Exception as e:
            raise QueryExecutionException(f"filter_family_by_nhts_status failed: {e}", "QRY_FILTER_FAMILY_NHTS") from e

    def filter_family_by_indigent_status(self, indigent_status_id: int) -> list[dict]:
        """
        Filter families by indigent status.
        """
        try:
            sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  COALESCE(h.household_num, '') AS household_num,
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  COALESCE(f.source_of_income, '') AS source_of_income,
                  
                  f.household_type_id,
                  f.nhts_status_id,
                  f.indigent_status_id
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                WHERE f.is_active IS TRUE
                  AND f.indigent_status_id = %s
                ORDER BY f.family_num;
            """
            
            rows = self._ctx.execute_query_to_dict(sql, [indigent_status_id])
            return rows or []
            
        except Exception as e:
            raise QueryExecutionException(f"filter_family_by_indigent_status failed: {e}", "QRY_FILTER_FAMILY_INDIGENT") from e

    def fetch_family_detail(self, family_id: int) -> Optional[dict]:
        """
        Fetch detailed information about a family including all members.
        """
        try:
            # Get family info
            family_sql = """
                SELECT
                  f.family_id,
                  f.family_num,
                  f.ufc_num,
                  f.source_of_income,
                  f.created_date,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS family_head_name,
                  
                  f.family_head_id,
                  COALESCE(h.household_num, '') AS household_num,
                  COALESCE(ht.household_type_name, '') AS household_type,
                  COALESCE(ns.nhts_status_name, '') AS nhts_status,
                  COALESCE(ins.indigent_status_name, '') AS indigent_status,
                  COALESCE(ir.income_range_amnt, '') AS monthly_income
                  
                FROM public.family_unit AS f
                LEFT JOIN public.person AS p ON p.person_id = f.family_head_id
                LEFT JOIN public.household_info AS h ON h.household_id = f.household_id
                LEFT JOIN public.household_type AS ht ON ht.household_type_id = f.household_type_id
                LEFT JOIN public.nhts_status AS ns ON ns.nhts_status_id = f.nhts_status_id
                LEFT JOIN public.indigent_status AS ins ON ins.indigent_status_id = f.indigent_status_id
                LEFT JOIN public.income_range AS ir ON ir.income_range_id = f.family_mnthly_icnome_id
                WHERE f.family_id = %s AND f.is_active IS TRUE;
            """
            
            family_rows = self._ctx.execute_query_to_dict(family_sql, [family_id])
            
            if not family_rows:
                return None
            
            family_data = family_rows[0]
            
            # Get family members
            members_sql = """
                SELECT
                  hm.house_member_id,
                  hm.person_id,
                  
                  TRIM(
                    CONCAT_WS(' ',
                      COALESCE(p.first_name, ''),
                      NULLIF(LEFT(COALESCE(p.middle_name, ''), 1) || '.', '.'),
                      COALESCE(p.last_name, ''),
                      COALESCE(p.suffix, '')
                    )
                  ) AS full_name,
                  
                  p.age,
                  COALESCE(s.sex_name, '') AS sex,
                  COALESCE(r1.relationship_name, '') AS relationship_to_household_head,
                  COALESCE(r2.relationship_name, '') AS relationship_to_family_head
                  
                FROM public.house_member AS hm
                LEFT JOIN public.person AS p ON p.person_id = hm.person_id
                LEFT JOIN public.sex AS s ON s.sex_id = p.sex_id
                LEFT JOIN public.relationship AS r1 ON r1.relationship_id = hm.relationship_to_hholdhead_id
                LEFT JOIN public.relationship AS r2 ON r2.relationship_id = hm.relationship_to_family_head_id
                WHERE hm.family_id = %s AND hm.is_active IS TRUE
                ORDER BY p.age DESC;
            """
            
            members_rows = self._ctx.execute_query_to_dict(members_sql, [family_id])
            
            family_data['members'] = members_rows or []
            
            return family_data
            
        except Exception as e:
            raise QueryExecutionException(f"fetch_family_detail failed: {e}", "E_DB") from e
