from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
)
from src.domain.contracts.resident_repository_contract import (
    IResidentRepository,
)

class ResidentRepository(IResidentRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_resident_list(self) -> list[ResidetDTO]:
        query = """
            SELECT
            p.person_id,
            p.person_code,
            CONCAT_WS(' ',
                NULLIF(p.last_name, ''),
                NULLIF(p.first_name, ''),
                NULLIF(p.middle_name, ''),
                NULLIF(p.suffix, '')
            ) AS full_name,
            CONCAT_WS(', ',
                NULLIF(a.street, ''),
                NULLIF(ps.purok_sitio_name, ''),
                NULLIF(a.barangay, ''),
                NULLIF(a.city, '')
            ) AS address,
            p.mobile_num AS mob_num,
            p.email
            FROM public.person p
            LEFT JOIN public.addresss a
            ON a.address_id = p.address_id
            LEFT JOIN public.purok_sitio ps
            ON ps.purok_sitio_id = a.purok_sitio_id
            JOIN public.residential_status rs
            ON rs.residential_status_id = p.residential_status_id
            WHERE UPPER(rs.residential_status_name) = 'RESIDENT'
            ORDER BY
            UPPER(NULLIF(p.last_name, '')),
            UPPER(NULLIF(p.first_name, '')),
            UPPER(NULLIF(p.middle_name, '')),
            UPPER(NULLIF(p.suffix, ''));
        """

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch resident list: {str(e)}") from e
        
    def search_resident(self, search: str) -> list[ResidetDTO]:
        try:
            query = "SELECT * FROM search_residents_by_name_ilike(%s)"
            rows = self._ctx.execute_query_to_dict(query, [search])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to search resident: {str(e)}") from e    
        
    def sort_purok(self, purok: int) -> list[ResidetDTO]:
        try:
            query = "SELECT * FROM filter_by_purok(%s)"
            rows = self._ctx.execute_query_to_dict(query, [purok])
            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to sort residents by purok: {str(e)}") from e
