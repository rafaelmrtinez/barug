from src.app.transfer_objects.request.child_visit_request import ChildVisitRequest
from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.maternal_exceptions import MaternalException
from src.infra.exceptions.query_exec_exception import QueryExecutionException


class MaternalRepository(IMaternalRepository):

    def __init__(self, ctx: IConnectionAdapter) -> None:
        self._ctx = ctx
        
    def get_child_record_by_person_id(self, person_id: int) -> int:
        print(f"Looking up child record for person_id: {person_id}")
        raw = """
            SELECT child_record_id FROM child_health_record WHERE person_id = %s;
        """
        params = [person_id]
        return self._ctx.execute_query_to_dict(raw, params)[0]['child_record_id']

    def insert_child_visit(self, data: ChildVisitRequest):        
        try:
            raw = """
                SELECT * FROM insert_child_visit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            params = [
                data.p_child_record_id,
                data.p_assessed_by_id,
                data.p_visit_date,
                data.p_feeding_type_id,
                data.p_referred_nbs_date,
                data.p_child_immunizations,
                data.p_bf_checks,
                data.p_monitoring_logs,
                data.p_screenings,
                data.p_iron_supplements,
                data.p_vitamin_a
            ]
            
            row = self._ctx.execute_query(raw, params)
        
            if not row:
                raise RuntimeError("No ID returned from insert_child_visit")
        
            return row[0]
        
        except QueryExecutionException as e:
            if MaternalException.is_maternal_exception(e.code):
                raise MaternalException(e.message) from e

    def insert_child_record(self, request: CreateChildRecordRequest) -> int:
        try:
            cmd = """
            SELECT * FROM create_child_health_record(%s, %s, %s, %s, %s, %s, %s); 
            """
            row = self._ctx.execute_query(cmd, [
                request.p_staff_id,
                request.p_person_id,
                request.p_mother_id,
                request.p_father_id,
                request.p_birth_order,
                request.p_delivery_place_type_id,
                request.p_family_id
            ])

            if not row:
                raise RuntimeError(
                    "No ID returned from create_child_health_record")

            return row[0]
        except QueryExecutionException as e:
            if MaternalException.is_maternal_exception(e.code):
                raise MaternalException(e.message) from e
