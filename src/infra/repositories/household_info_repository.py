from src.infra.contracts.connection_adapter import IConnectionAdapter


class HouseholdInfoRepository:

    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        
    def get_family_members_by_family_id(self, family_id):
        sql = """
            SELECT 
            house_member.house_member_id,
            CONCAT(person.first_name, ', ', COALESCE(person.middle_name), ', ', person.last_name, ', ', COALESCE(person.suffix)) AS "Member"
            FROM house_member
            INNER JOIN person
            ON person.person_id = house_member.person_id
            WHERE house_member.family_id = %s;
        """
        params = [family_id]
        rows = self._ctx.execute_query(sql, params)
        return rows

    def get_basic_family_unit_details_by_household_id(self, household_id: int):
        sql = """
            SELECT 
            fu.household_id,
            fu.family_num,
            fu.family_id, 
            CONCAT(ph.first_name, ' ', COALESCE(ph.middle_name,''), ' ', ph.last_name, ' ', COALESCE(ph.suffix,'')) AS family_head,
            ht.household_type_name,
            ns.nhts_status_name,
            ir.income_range_amnt,
            fu.source_of_income,
            indigent_status.indigent_status_name,
            JSON_AGG(
                JSON_BUILD_OBJECT(
                    'name', CONCAT(pm.first_name, ' ', COALESCE(pm.middle_name,''), ' ', pm.last_name, ' ', COALESCE(pm.suffix,'')),
                    'relation', rel.relationship_name,
                    'age', pm.age,
                    'sex', sex.sex_name
                )
            ) AS members
        FROM family_unit fu
        INNER JOIN person ph
            ON ph.person_id = fu.family_head_id
        INNER JOIN household_type ht
            ON ht.household_type_id = fu.household_type_id
        INNER JOIN nhts_status ns
            ON ns.nhts_status_id = fu.nhts_status_id
        INNER JOIN income_range ir
            ON ir.income_range_id = fu.family_mnthly_icnome_id
        INNER JOIN household_info hi
            ON hi.household_id = fu.household_id
        INNER JOIN indigent_status
            ON indigent_status.indigent_status_id = fu.indigent_status_id
        LEFT JOIN house_member hm
            ON hm.family_id = fu.family_id
        LEFT JOIN person pm
            ON pm.person_id = hm.person_id
        LEFT JOIN relationship rel
            ON rel.relationship_id = hm.relationship_to_family_head_id
        LEFT JOIN sex
            ON sex.sex_id = pm.sex_id
        WHERE hi.household_id = %s
        GROUP BY fu.household_id, fu.family_num, fu.family_id,
                ph.first_name, ph.middle_name, ph.last_name, ph.suffix,
                ht.household_type_name, ns.nhts_status_name,
                ir.income_range_amnt, fu.source_of_income, indigent_status.indigent_status_name;

        """
        params = [household_id]
        rows = self._ctx.execute_query_to_dict(sql, params)
        return rows
    
    def get_basic_info_by_id(self, id: int):
        sql = """
            SELECT
            CONCAT(person.first_name, ', ', COALESCE(person.middle_name), ', ', person.last_name, ', ', COALESCE(person.suffix)) AS HEAD,
            household_info.house_number,
            house_type.house_type_name,
            house_ownership.house_ownership_name,
            CONCAT(purok_sitio.purok_sitio_code, ' ', purok_sitio.purok_sitio_name, ' ', addresss.street, ' ', addresss.barangay, ' ', addresss.city) 
            FROM 
            household_info 
            INNER JOIN person
            ON person.person_id = household_info.household_head_id
            INNER JOIN house_type
            ON house_type.house_type_id = household_info.house_type_id
            INNER JOIN house_ownership
            ON house_ownership.house_ownership_id = household_info.house_ownership_id
            INNER JOIN addresss
            ON addresss.address_id = household_info.address_id
            INNER JOIN purok_sitio
            ON purok_sitio.purok_sitio_id = addresss.purok_sitio_id
            WHERE household_id = %s;
        """
        params = [id]
        rows = self._ctx.execute_query(sql, params)
        
        if rows:
            household_details = rows[0]
            
        household_details = {
            'household_head': household_details[0],
            'household_num': household_details[1],
            'house_type': household_details[2],
            'house_ownership': household_details[3],
            'address': household_details[4],
        }
        
        return household_details