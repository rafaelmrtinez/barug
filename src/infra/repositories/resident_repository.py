from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
)
from src.domain.contracts.resident_repository_contract import (
    IResidentRepository,
)

class ResidentRepository(IResidentRepository):
    def __init__(self, connection_adapter: IConnectionAdapter) -> None:
        self._connection_adapter = connection_adapter

    def fetch_resident_list(self) -> list[ResidetDTO]:
        query = """
            SELECT
                person_id,
                person_code,
                full_name,
                address,
                mob_num,
                email
            FROM
                residents
            ORDER BY
                full_name ASC;
        """

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch resident list: {str(e)}") from e
        
    def search_resident(self, search):
        query = """
            SELECT
                person_id,
                person_code,
                full_name,
                address,
                mob_num,
                email
            FROM
                residents
            WHERE
                full_name ILIKE %s OR
                person_code ILIKE %s
            ORDER BY
                full_name ASC;
        """
        search_param = f"%{search}%"

        try:
            rows = self._ctx.execute_query_to_dict(query, [search_param, search_param])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to search resident: {str(e)}") from e    
        
    def sort_purok(self, purok):
        query = """
            SELECT
                person_id,
                person_code,
                full_name,
                address,
                mob_num,
                email
            FROM
                residents
            WHERE
                purok = %s
            ORDER BY
                full_name ASC;
        """

        try:
            rows = self._ctx.execute_query_to_dict(query, [purok])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to sort residents by purok: {str(e)}") from e
