from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)
from src.domain.contracts.or_repository_contract import (
    IORRepository,
)

class ORRepository(IORRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_or_list(self) -> list[ORDTO]:
        query = "SELECT * FROM treasurer_or_payment_summary()"

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch OR list: {str(e)}") from e
        
    def search_or_list(self, search: str) -> list[ORDTO]:

        try:
            sql = "SELECT * FROM treasurer_search_payments_by_purpose(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [search])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to search OR list: {str(e)}") from e
        
    def filter_by_payment_method(self, payment_method: int) -> list[ORDTO]:
        try:
            query = "SELECT * FROM treasurer_search_payments_by_method_id(%s)"
            rows = self._ctx.execute_query_to_dict(query, [payment_method])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to filter OR list by payment method: {str(e)}") from e