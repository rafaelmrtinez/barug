from src.app.transfer_objects.response.child_basic_info_response import BasicInformationResponse
from src.infra.contracts.child_repository import IChildRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter


class ChildRepository(IChildRepository):
    
    def __init__(self, ctx: IConnectionAdapter) -> None:
        self.ctx = ctx
        
    def fetch_child_health_record_by_person_id(self, id: int) -> int:
        raw = """
        SELECT child_record_id FROM child_health_record WHERE person_id = %s;"""
        params = [id]
        return self.ctx.execute_query_to_dict(raw, params)[0]["child_record_id"]

    def get_child_basic_info_by_person_id(self, id: int) -> BasicInformationResponse:
        
        raw = """
            SELECT 
            family_unit.family_num AS FAM_NUMBER,
            CONCAT(child.first_name, ' ', COALESCE(child.middle_name, ''), ' ', child.last_name, ' ', COALESCE(child.suffix, '')) AS CHILD,
            CONCAT(mother.first_name, ' ', COALESCE(mother.middle_name, ''), ' ', mother.last_name, ' ', COALESCE(mother.suffix, '')) AS MOTHER,
            CONCAT(father.first_name, ' ', COALESCE(father.middle_name, ''), ' ', father.last_name, ' ', COALESCE(father.suffix, '')) AS FATHER,
            child_health_record.birth_order AS BIRTH_ORDER,
            delivery_place_type.delivery_place_type_name as PLACE_OF_DELIVERY,
            mother.age AS MOTHERS_AGE,
            father.age AS FATHERS_AGE
            FROM child_health_record
            INNER JOIN person AS child 
            ON child.person_id = child_health_record.person_id
            INNER JOIN person AS mother 
            ON mother.person_id = child_health_record.mother_id
            INNER JOIN person AS father 
            ON father.person_id = child_health_record.father_id
            INNER JOIN family_unit
            ON family_unit.family_id = child_health_record.family_id
            INNER JOIN delivery_place_type
            ON delivery_place_type.delivery_place_type_id = child_health_record.delivery_place_type_id
            WHERE child_health_record.person_id = %s;
        """
        
        params = [id]
        result = self.ctx.execute_query_to_dict(raw, params)[0]
        return BasicInformationResponse(**result)