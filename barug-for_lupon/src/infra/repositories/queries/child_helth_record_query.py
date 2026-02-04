from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.utilities.age_calculator import AgeCalculator


class ChildHealthRecordQuery:
    
    def __init__(self, connection: IConnectionAdapter):
        self._connection = connection

    def fetch_all(self) -> list[dict]:
        """Return all child health records with related person, family and address info."""
        sql = """
        SELECT
            c.*,
            p.person_id AS person_person_id,
            -- compute child's age in years from person.birthdate
            CASE WHEN p.birthdate IS NOT NULL THEN date_part('year', age(CURRENT_DATE, p.birthdate))::int ELSE NULL END AS child_age,
            -- build a readable full name
            regexp_replace(concat_ws(' ', NULLIF(p.first_name,''), NULLIF(LEFT(COALESCE(p.middle_name,''),1) || '.', '.'), NULLIF(p.last_name,''), NULLIF(p.suffix,'')), '\\s+', ' ', 'g') AS full_name,
            -- parent's names
            regexp_replace(concat_ws(' ', NULLIF(pm.first_name,''), NULLIF(LEFT(COALESCE(pm.middle_name,''),1) || '.', '.'), NULLIF(pm.last_name,''), NULLIF(pm.suffix,'')), '\\s+', ' ', 'g') AS mother_full_name,
            regexp_replace(concat_ws(' ', NULLIF(pf.first_name,''), NULLIF(LEFT(COALESCE(pf.middle_name,''),1) || '.', '.'), NULLIF(pf.last_name,''), NULLIF(pf.suffix,'')), '\\s+', ' ', 'g') AS father_full_name,
            fu.family_num,
            fu.ufc_num,
            hh.household_num,
            a.street,
            a.barangay,
            a.city,
            ps.purok_sitio_name
        FROM public.child_health_record c
        LEFT JOIN public.person p ON p.person_id = c.person_id
        LEFT JOIN public.person pm ON pm.person_id = c.mother_id
        LEFT JOIN public.person pf ON pf.person_id = c.father_id
        LEFT JOIN public.family_unit fu ON fu.family_id = c.family_id
        LEFT JOIN public.household_info hh ON hh.household_id = fu.household_id
        LEFT JOIN public.addresss a ON a.address_id = hh.address_id
        LEFT JOIN public.purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
        ORDER BY c.created_at DESC, c.child_record_id DESC
        """
        try:
            rows = self._connection.execute_query_to_dict(sql, None)
            return rows or []
        except Exception:
            raise

    def fetch_by_child_id(self, child_record_id: int) -> dict | None:
        """Return a single child health record (with related info) by child_record_id."""
        sql = """
        SELECT
            c.*,
            p.person_id AS person_person_id,
            p.age AS child_age,
            regexp_replace(concat_ws(' ', NULLIF(p.first_name,''), NULLIF(LEFT(COALESCE(p.middle_name,''),1) || '.', '.'), NULLIF(p.last_name,''), NULLIF(p.suffix,'')), '\\s+', ' ', 'g') AS full_name,
            regexp_replace(concat_ws(' ', NULLIF(pm.first_name,''), NULLIF(LEFT(COALESCE(pm.middle_name,''),1) || '.', '.'), NULLIF(pm.last_name,''), NULLIF(pm.suffix,'')), '\\s+', ' ', 'g') AS mother_full_name,
            regexp_replace(concat_ws(' ', NULLIF(pf.first_name,''), NULLIF(LEFT(COALESCE(pf.middle_name,''),1) || '.', '.'), NULLIF(pf.last_name,''), NULLIF(pf.suffix,'')), '\\s+', ' ', 'g') AS father_full_name,
            fu.family_num,
            fu.ufc_num,
            hh.household_num,
            a.street,
            a.barangay,
            a.city,
            ps.purok_sitio_name
        FROM public.child_health_record c
        LEFT JOIN public.person p ON p.person_id = c.person_id
        LEFT JOIN public.person pm ON pm.person_id = c.mother_id
        LEFT JOIN public.person pf ON pf.person_id = c.father_id
        LEFT JOIN public.family_unit fu ON fu.family_id = c.family_id
        LEFT JOIN public.household_info hh ON hh.household_id = fu.household_id
        LEFT JOIN public.addresss a ON a.address_id = hh.address_id
        LEFT JOIN public.purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
        WHERE c.child_record_id = %s
        LIMIT 1
        """
        try:
            rows = self._connection.execute_query_to_dict(sql, (child_record_id,))
            return rows[0] if rows else None
        except Exception:
            raise

    def fetch_by_person_id(self, person_id: int) -> dict | None:
        """Return the most recent child_health_record for the given person_id (if any)."""
        sql = """
        SELECT
            c.*,
            p.person_id AS person_person_id,
            p.age AS child_age,
            regexp_replace(concat_ws(' ', NULLIF(p.first_name,''), NULLIF(LEFT(COALESCE(p.middle_name,''),1) || '.', '.'), NULLIF(p.last_name,''), NULLIF(p.suffix,'')), '\\s+', ' ', 'g') AS full_name,
            regexp_replace(concat_ws(' ', NULLIF(pm.first_name,''), NULLIF(LEFT(COALESCE(pm.middle_name,''),1) || '.', '.'), NULLIF(pm.last_name,''), NULLIF(pm.suffix,'')), '\\s+', ' ', 'g') AS mother_full_name,
            regexp_replace(concat_ws(' ', NULLIF(pf.first_name,''), NULLIF(LEFT(COALESCE(pf.middle_name,''),1) || '.', '.'), NULLIF(pf.last_name,''), NULLIF(pf.suffix,'')), '\\s+', ' ', 'g') AS father_full_name,
            fu.family_num,
            fu.ufc_num,
            hh.household_num,
            a.street,
            a.barangay,
            a.city,
            ps.purok_sitio_name
        FROM public.child_health_record c
        LEFT JOIN public.person p ON p.person_id = c.person_id
        LEFT JOIN public.person pm ON pm.person_id = c.mother_id
        LEFT JOIN public.person pf ON pf.person_id = c.father_id
        LEFT JOIN public.family_unit fu ON fu.family_id = c.family_id
        LEFT JOIN public.household_info hh ON hh.household_id = fu.household_id
        LEFT JOIN public.addresss a ON a.address_id = hh.address_id
        LEFT JOIN public.purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
        WHERE c.person_id = %s
        ORDER BY c.created_at DESC, c.child_record_id DESC
        LIMIT 1
        """
        try:
            rows = self._connection.execute_query_to_dict(sql, (person_id,))
            return rows[0] if rows else None
        except Exception:
            raise