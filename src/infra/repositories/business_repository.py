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

    def search_owner(self, search: str) -> list[ResidentOwnerDTO]:
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
                    full_name=r.get("person_name"),
                    address_line=_addr(r),
                    street=r.get("street"),
                    purok=r.get("purok"),
                    barangay=r.get("barangay"),
                    city=r.get("city"),
                    # fields your SQL doesn't return yet — leave None
                    sex_name=None,
                    date_of_birth=None,
                    residential_status_name=None,
                    civil_status=None,
                    nationality=None,
                    religion=None,
                    mobile=None,
                    email=None,
                )
                for r in rows or []
            ]

        except Exception as e:
            raise QueryExecutionException(f"search_owner failed: {e}") from e
        
    def get_owner_details(self, person_id: int) -> list[ResidentOwnerDTO]:
        try:
            sql = "SELECT * FROM get_details(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [person_id]) or []

            if not rows:
                return None
            r = rows[0]

            def _addr(r: dict) -> str | None:
                parts = [r.get("street"), r.get("purok"), r.get("barangay"), r.get("city")]
                parts = [p for p in parts if p and str(p).strip()]
                return ", ".join(parts) if parts else None
            
            def _compose_full_name(r: dict) -> str:
                last   = (r.get("last_name") or "").strip()
                first  = (r.get("first_name") or "").strip()
                middle = (r.get("middle_name") or "").strip()
                suffix = (r.get("suffix") or "").strip()

                # build "LAST, FIRST"
                main = ", ".join([x for x in (last, first) if x])

                # middle initial "M." only if middle exists
                mi = f"{middle[0]}." if middle else ""

                parts = [p for p in (main, mi, suffix) if p]
                return " ".join(parts) if parts else ""
            
            full_name = r.get("full_name") or _compose_full_name(r)

            return ResidentOwnerDTO(
                person_id=r["person_id"],
                person_code=r.get("person_code"),
                full_name=full_name,
                sex_name=r.get("sex"),
                date_of_birth=r.get("birthdate"),
                residential_status_name= r.get("residential_status"),
                civil_status=r.get("civil_status"),
                nationality=r.get("nationality"),
                religion=r.get("religion"),
                mobile=r.get("mobile_num"),
                email=r.get("email"),
                street=r.get("street"),
                purok=r.get("purok"),
                barangay=r.get("barangay"),
                city=r.get("city"),
                address_line=_addr(r),
            )
        except Exception as e:
            raise QueryExecutionException(f"get_owner_details failed: {e}") from e