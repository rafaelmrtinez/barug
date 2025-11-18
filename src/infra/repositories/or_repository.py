from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)
from src.domain.contracts.or_repository_contract import (
    IORRepository,
)

class ORRepository(IORRepository):
    def __init__(self, connection_adapter: IConnectionAdapter) -> None:
        self._connection_adapter = connection_adapter

    def fetch_or_list(self) -> list[ORDTO]:
        query = """
            SELECT
                or_number,
                payment_method,
                amount,
                purpose,
                issued_by,
                issued_at
            FROM
                official_receipts
            ORDER BY
                issued_at DESC;
        """

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch OR list: {str(e)}") from e