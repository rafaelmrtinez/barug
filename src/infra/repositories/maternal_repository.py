from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.maternal_exceptions import MaternalException
from src.infra.exceptions.query_exec_exception import QueryExecutionException


class MaternalRepository:

    def __init__(self, ctx: IConnectionAdapter) -> None:
        self._ctx = ctx

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
