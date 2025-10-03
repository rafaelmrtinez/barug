from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository    
)
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

class BusinessRepository(IBusinessRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_business_list(self) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM get_business_summary();"
            rows = self._ctx.execute_query_to_dict(sql, [])

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"fetch_business_list failed: {e}") from e
        
    def search_business(self, search: str) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM search_business_summaries(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [search])

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"search_business failed: {e}") from e
        
    def sort_b_type(self, b_type_id: int) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM filter_business_summaries_by_type(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [b_type_id])

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_b_type failed: {e}") from e
        
    def sort_ownership_type(self, ownership_type_id: int) -> list[BusinessListDTO]:
        try:
            sql ="SELECT * FROM filter_business_summaries_by_ownership(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [ownership_type_id])

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_ownership_type failed: {e}") from e
    
    def sort_status(self, status_id: int) -> list[BusinessListDTO]:
        try:
            sql = "SELECT * FROM filter_business_summaries_by_status(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [status_id])

            return self._map(rows)
        except Exception as e:
            raise QueryExecutionException(f"sort_status failed: {e}") from e
    
    def _map(self, rows: list[dict]) -> list[BusinessListDTO]:
        # Ensure your SQL functions include ownership_type_name as a column.
        mapped: list[BusinessListDTO] = []
        for r in rows:
            mapped.append(
                BusinessListDTO(
                    business_id=r["business_id"],
                    business_name=r["business_name"],
                    business_type_name=r["business_type_name"],
                    business_nature=r["business_nature"],
                    business_owner_name=r["business_owner_name"],
                    business_address=r["business_address"],
                    business_status_name=r["business_status_name"],
                    ownership_type_name=r.get("ownership_type_name", ""),  # safe-get
                )
            )
        return mapped
    
class ResidentOwnerRepository(IResidentOwnerRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def search_owner(self, search: str):
        try: 
            sql = "SELECT * FROM search_person_by_code_or_name(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [search])

            def _addr(r: dict) -> str | None:
                parts = [r.get("street"), r.get("purok"), r.get("barangay"), r.get("city")]
                joined = ", ".join(p for p in parts if p and str(p).strip() != "")
                return joined or None

            return [
                ResidentOwnerDTO(
                    person_id=r["person_id"],
                    person_code=r.get("person_code"),
                    full_name=r.get("person_name"),     # note: your SQL names this 'person_name'
                    sex_name=None,                      # not provided by the SQL; extend SQL if needed
                    date_of_birth=None,                 # "
                    address_line=_addr(r),
                    residential_status_name=None,       # "
                    mobile=None,                        # "
                    email=None,                         # "
                    street=r.get("street"),
                    purok=r.get("purok"),
                    barangay=r.get("barangay"),
                    city=r.get("city"),
                )
                for r in rows
            ]

        except Exception as e:
            raise QueryExecutionException(f"search_owner failed: {e}") from e