
from src.infra.database.connection_adapter import ConnectionAdapter
import logging


class HouseholdQuery:
    _logger = logging.getLogger("HouseholdQuery")
    
    def __init__(self, ctx: ConnectionAdapter):
        self._ctx = ctx
        self._logger.debug("HouseholdQuery initialized.")
        
    # 1. Individual table queries
    def get_household_by_id(self, household_id):
        self._logger.info(f"Querying household by ID.")
        sql = """
        SELECT * FROM household_info WHERE household_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (household_id,))

    def get_family_units_by_household(self, household_id):
        self._logger.info("Querying family units for household.")
        sql = """
        SELECT * FROM family_unit WHERE household_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (household_id,))

    def get_house_members_by_family(self, family_id):
        self._logger.info("Querying house members for family.")
        sql = """
        SELECT * FROM house_member WHERE family_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (family_id,))

    def get_person_by_id(self, person_id):
        self._logger.info("Querying person by ID.")
        sql = """
        SELECT * FROM person WHERE person_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (person_id,))

    def get_address_by_id(self, address_id):
        self._logger.info("Querying address by ID.")
        sql = """
        SELECT * FROM addresss WHERE address_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (address_id,))

    def get_purok_sitio_by_id(self, purok_sitio_id):
        self._logger.info("Querying purok/sitio by ID.")
        sql = """
        SELECT * FROM purok_sitio WHERE purok_sitio_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (purok_sitio_id,))

    def get_relationships(self):
        self._logger.info("Querying all relationships.")
        sql = "SELECT * FROM relationship"
        return self._ctx.execute_query_to_dict(sql)

    def get_income_ranges(self):
        self._logger.info("Querying all income ranges.")
        sql = "SELECT * FROM income_range"
        return self._ctx.execute_query_to_dict(sql)

    def get_indigent_statuses(self):
        self._logger.info("Querying all indigent statuses.")
        sql = "SELECT * FROM indigent_status"
        return self._ctx.execute_query_to_dict(sql)

    def get_household_types(self):
        self._logger.info("Querying all household types.")
        sql = "SELECT * FROM household_type"
        return self._ctx.execute_query_to_dict(sql)

    def get_house_ownerships(self):
        self._logger.info("Querying all house ownerships.")
        sql = "SELECT * FROM house_ownership"
        return self._ctx.execute_query_to_dict(sql)

    def get_house_types(self):
        self._logger.info("Querying all house types.")
        sql = "SELECT * FROM house_type"
        return self._ctx.execute_query_to_dict(sql)

    def get_sexes(self):
        self._logger.info("Querying all sexes.")
        sql = "SELECT * FROM sex"
        return self._ctx.execute_query_to_dict(sql)

    def get_person_statuses(self):
        self._logger.info("Querying all person statuses.")
        sql = "SELECT * FROM person_status"
        return self._ctx.execute_query_to_dict(sql)

    def get_residential_statuses(self):
        self._logger.info("Querying all residential statuses.")
        sql = "SELECT * FROM residential_status"
        return self._ctx.execute_query_to_dict(sql)

    def get_civil_statuses(self):
        self._logger.info("Querying all civil statuses.")
        sql = "SELECT * FROM civil_status"
        return self._ctx.execute_query_to_dict(sql)

    def get_nationalities(self):
        self._logger.info("Querying all nationalities.")
        sql = "SELECT * FROM nationality"
        return self._ctx.execute_query_to_dict(sql)

    def get_religions(self):
        self._logger.info("Querying all religions.")
        sql = "SELECT * FROM religion"
        return self._ctx.execute_query_to_dict(sql)

    def get_educational_attainments(self):
        self._logger.info("Querying all educational attainments.")
        sql = "SELECT * FROM educational_attainment"
        return self._ctx.execute_query_to_dict(sql)

    def get_employment_statuses(self):
        self._logger.info("Querying all employment statuses.")
        sql = "SELECT * FROM employment_status"
        return self._ctx.execute_query_to_dict(sql)

    def get_registration_methods(self):
        self._logger.info("Querying all registration methods.")
        sql = "SELECT * FROM registration_method"
        return self._ctx.execute_query_to_dict(sql)

    def get_staff_by_id(self, staff_id):
        self._logger.info("Querying staff by ID.")
        sql = "SELECT * FROM staff WHERE staff_id = %s"
        return self._ctx.execute_query_to_dict(sql, (staff_id,))

    # 2. Full household profile (all related tables)
    def get_full_household_profile(self, household_id):
        self._logger.info("Querying full household profile.")
        sql = """
        SELECT h.*, a.*, ps.*, ht.*, ho.*, rm.*, hh.*, f.*, hm.*, p.*
        FROM household_info h
        LEFT JOIN addresss a ON h.address_id = a.address_id
        LEFT JOIN purok_sitio ps ON a.purok_sitio_id = ps.purok_sitio_id
        LEFT JOIN household_type ht ON h.household_type_id = ht.household_type_id
        LEFT JOIN house_ownership ho ON h.house_ownership_id = ho.house_ownership_id
        LEFT JOIN registration_method rm ON h.registration_method_id = rm.registration_method_id
        LEFT JOIN person hh ON h.household_head_id = hh.person_id
        LEFT JOIN family_unit f ON h.household_id = f.household_id
        LEFT JOIN house_member hm ON f.family_id = hm.family_id
        LEFT JOIN person p ON hm.person_id = p.person_id
        WHERE h.household_id = %s
        """
        return self._ctx.execute_query_to_dict(sql, (household_id,))

    # 3. Search mechanisms
    def search_households_by_num(self, household_num):
        self._logger.info("Searching households by number.")
        sql = "SELECT * FROM household_info WHERE household_num ILIKE %s"
        return self._ctx.execute_query_to_dict(sql, (f'%{household_num}%',))

    def search_person_by_name(self, name):
        self._logger.info("Searching person by name.")
        sql = """
        SELECT * FROM person WHERE 
            first_name ILIKE %s OR last_name ILIKE %s OR middle_name ILIKE %s
        """
        like = f'%{name}%'
        return self._ctx.execute_query_to_dict(sql, (like, like, like))

    def search_address(self, street=None, barangay=None, city=None):
        self._logger.info("Searching address.")
        conditions = []
        params = []
        if street:
            conditions.append("street ILIKE %s")
            params.append(f'%{street}%')
        if barangay:
            conditions.append("barangay ILIKE %s")
            params.append(f'%{barangay}%')
        if city:
            conditions.append("city ILIKE %s")
            params.append(f'%{city}%')
        sql = "SELECT * FROM addresss"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return self._ctx.execute_query_to_dict(sql, tuple(params))

    def search_family_unit_by_num(self, family_num):
        self._logger.info("Searching family unit by number.")
        sql = "SELECT * FROM family_unit WHERE family_num ILIKE %s"
        return self._ctx.execute_query_to_dict(sql, (f'%{family_num}%',))

    def search_house_member_by_person(self, person_id):
        self._logger.info("Searching house member by person ID.")
        sql = "SELECT * FROM house_member WHERE person_id = %s"
        return self._ctx.execute_query_to_dict(sql, (person_id,))
    
