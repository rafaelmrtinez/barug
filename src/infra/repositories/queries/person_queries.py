from src.infra.contracts.connection_adapter import IConnectionAdapter


class PersonQuery:
    def __init__(self, db: IConnectionAdapter):
        self.db = db

    def get_person_by_id(self, person_id: int) -> dict:
        """Return a Person DTO (dict) for the given `person_id` or empty dict.

        The DTO contains direct person columns plus resolved lookup names for
        sex, civil status, nationality, religion, education, employment status,
        registration method, person status, residential status, income range,
        and family summary. Address and purok fields are included when present.
        """
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_id = %s
        LIMIT 1
        """

        rows = self.db.execute_query_to_dict(query, (person_id,))
        return rows[0] if rows else {}

    def get_person_by_code(self, person_code: str) -> dict:
        """Return a Person DTO (dict) for the given `person_code` or empty dict."""
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_code = %s
        LIMIT 1
        """

        rows = self.db.execute_query_to_dict(query, (person_code,))
        return rows[0] if rows else {}

    def get_active_people(self, limit: int | None = None) -> list:
        """Return a list of Person DTOs for people with ACTIVE status.

        The method returns the same DTO shape as `get_person_by_id`/`get_person_by_code`,
        but for all persons whose `person_status_id` indicates ACTIVE (1).
        Optionally limit the number of returned rows with `limit`.
        """
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
        ORDER BY p.last_name, p.first_name
        """

        params = None
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []
        
    def get_female_active(self, limit: int | None = None) -> list:
        """Return a list of active female residents.

        Filters: `person_status_id = 1` (ACTIVE) and `sex_id = 2` (FEMALE).
        Returns the same DTO shape as `get_active_people`.
        """
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.sex_id = 2
        ORDER BY p.last_name, p.first_name
        """

        params = None
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []
        
    def get_minors_under5_active(self, limit: int | None = None) -> list:
        """Return a list of Person DTOs who are active and under 5 years old.

        Computes age from `p.birthdate` and returns persons where age < 5 years
        and `person_status_id = 1` (ACTIVE). Optional `limit` parameter limits
        the number of returned rows.
        """
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num,
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT AS age_years
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.birthdate IS NOT NULL
          AND p.birthdate <= CURRENT_DATE
          AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT < 5
        ORDER BY p.last_name, p.first_name
        """

        params = None
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []

    def search_active_people_by_key(self, key: str, limit: int | None = None) -> list:
        """Search active people using a free-text `key` matched with ILIKE.

        Matches against concatenated name, person_code, street, purok, barangay, and city.
        Returns the same DTO shape as `get_active_people`.
        """
        pattern = f"%{key}%"
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND (
            CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix) ILIKE %s OR
            p.person_code ILIKE %s OR
            a.street ILIKE %s OR
            ps.purok_sitio_name ILIKE %s OR
            a.barangay ILIKE %s OR
            a.city ILIKE %s
          )
        ORDER BY p.last_name, p.first_name
        """

        params = (pattern, pattern, pattern, pattern, pattern, pattern)
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = params + (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []

    def search_female_active_by_key(self, key: str, limit: int | None = None) -> list:
        """Search active female residents using a free-text `key` matched with ILIKE."""
        pattern = f"%{key}%"
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.sex_id = 2
          AND (
            CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix) ILIKE %s OR
            p.person_code ILIKE %s OR
            a.street ILIKE %s OR
            ps.purok_sitio_name ILIKE %s OR
            a.barangay ILIKE %s OR
            a.city ILIKE %s
          )
        ORDER BY p.last_name, p.first_name
        """

        params = (pattern, pattern, pattern, pattern, pattern, pattern)
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = params + (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []

    def search_female_active_resident_by_key(self, key: str, limit: int | None = None) -> list:
        """Search active female residents who are also marked as RESIDENT using a free-text `key` matched with ILIKE.

        This is a copy of `search_female_active_by_key` but adds a condition that the
        residential status name equals 'RESIDENT' (case-insensitive).
        """
        pattern = f"%{key}%"
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.sex_id = 2
          AND UPPER(rs.residential_status_name) = 'RESIDENT'
          AND (
            CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix) ILIKE %s OR
            p.person_code ILIKE %s OR
            a.street ILIKE %s OR
            ps.purok_sitio_name ILIKE %s OR
            a.barangay ILIKE %s OR
            a.city ILIKE %s
          )
        ORDER BY p.last_name, p.first_name
        """

        params = (pattern, pattern, pattern, pattern, pattern, pattern)
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = params + (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []

    def search_minors_under5_active_by_key(self, key: str, limit: int | None = None) -> list:
        """Search active minors under 5 using a free-text `key` matched with ILIKE."""
        pattern = f"%{key}%"
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num,
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT AS age_years
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.birthdate IS NOT NULL
          AND p.birthdate <= CURRENT_DATE
          AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT < 5
          AND (
            CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix) ILIKE %s OR
            p.person_code ILIKE %s OR
            a.street ILIKE %s OR
            ps.purok_sitio_name ILIKE %s OR
            a.barangay ILIKE %s OR
            a.city ILIKE %s
          )
        ORDER BY p.last_name, p.first_name
        """

        params = (pattern, pattern, pattern, pattern, pattern, pattern)
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = params + (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []
        
    def search_minors_under5_active_resident_by_key(self, key: str, limit: int | None = None) -> list:
        """Search active minors under 5 who are also marked as RESIDENT using a free-text `key` matched with ILIKE.

        This is a copy of `search_minors_under5_active_by_key` but adds a condition that the
        residential status name equals 'RESIDENT' (case-insensitive).
        """
        pattern = f"%{key}%"
        query = """
        SELECT DISTINCT
            p.*,
            CONCAT(p.first_name, ' ',
                   CASE WHEN p.middle_name IS NOT NULL AND p.middle_name <> '' THEN
                       SUBSTRING(p.middle_name FROM 1 FOR 1) || '. '
                   ELSE '' END,
                   p.last_name,
                   CASE WHEN p.suffix IS NOT NULL AND p.suffix <> '' THEN
                       ' ' || p.suffix
                   ELSE '' END) AS full_name,
            CONCAT(a.street, ', ',
                   CASE WHEN ps.purok_sitio_name IS NOT NULL AND ps.purok_sitio_name <> '' THEN
                       ps.purok_sitio_name || ', '
                   ELSE '' END,
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN
                       'Brgy ' || a.barangay || ', '
                   ELSE '' END,
                   CASE WHEN a.city IS NOT NULL AND a.city <> '' THEN
                       a.city
                   ELSE '' END) AS full_address,
            ir.income_range_amnt AS income_range,
            a.street, a.barangay, a.city, a.latitude, a.longitude, a.purok_sitio_id AS address_purok_id,
            ps.purok_sitio_code AS purok_code, ps.purok_sitio_name AS purok_name,
            s.sex_name,
            pst.person_status_name,
            rs.residential_status_name,
            cs.civil_status_name,
            n.nationality_name,
            r.religion_name,
            ea.educ_level AS education_level,
            es.employment_status_name,
            rm.registration_method_name,
            fu.family_id, fu.family_num, fu.ufc_num,
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT AS age_years
        FROM person p
        LEFT JOIN income_range ir ON p.mnthly_personal_income_id = ir.income_range_id
        LEFT JOIN addresss a ON p.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN sex s ON p.sex_id = s.sex_id
        LEFT JOIN person_status pst ON p.person_status_id = pst.person_status_id
        LEFT JOIN residential_status rs ON p.residential_status_id = rs.residential_status_id
        LEFT JOIN civil_status cs ON p.civil_status_id = cs.civil_status_id
        LEFT JOIN nationality n ON p.nationality_id = n.nationality_id
        LEFT JOIN religion r ON p.religion_id = r.religion_id
        LEFT JOIN educational_attainment ea ON p.education_id = ea.education_id
        LEFT JOIN employment_status es ON p.employment_status_id = es.employment_status_id
        LEFT JOIN registration_method rm ON p.registration_method_id = rm.registration_method_id
        LEFT JOIN family_unit fu ON fu.family_head_id = p.person_id
        WHERE p.person_status_id = 1
          AND p.birthdate IS NOT NULL
          AND p.birthdate <= CURRENT_DATE
          AND EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))::INT < 5
          AND UPPER(rs.residential_status_name) = 'RESIDENT'
          AND (
            CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix) ILIKE %s OR
            p.person_code ILIKE %s OR
            a.street ILIKE %s OR
            ps.purok_sitio_name ILIKE %s OR
            a.barangay ILIKE %s OR
            a.city ILIKE %s
          )
        ORDER BY p.last_name, p.first_name
        """

        params = (pattern, pattern, pattern, pattern, pattern, pattern)
        if limit is not None:
            query = query + "\nLIMIT %s"
            params = params + (limit,)

        rows = self.db.execute_query_to_dict(query, params)
        return rows or []
    
