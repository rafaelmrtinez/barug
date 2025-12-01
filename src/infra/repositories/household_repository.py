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
                -- WHERE h.is_active IS TRUE
                ORDER BY h.created_date DESC, h.household_num;
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
