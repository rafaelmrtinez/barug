from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)
from src.domain.contracts.or_repository_contract import (
    IORRepository,
)
from typing import Optional

class ORRepository(IORRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_or_list(self) -> list[ORDTO]:
        query = "SELECT * FROM treasurer_or_payment_summary()"

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch OR list: {str(e)}", 500) from e
        
    def search_or_list(self, search: str) -> list[ORDTO]:

        try:
            sql = "SELECT * FROM treasurer_search_payments_by_purpose(%s)"
            rows = self._ctx.execute_query_to_dict(sql, [search])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to search OR list: {str(e)}", 500) from e
        
    def filter_by_payment_method(self, payment_method: int) -> list[ORDTO]:
        try:
            query = "SELECT * FROM treasurer_search_payments_by_method_id(%s)"
            rows = self._ctx.execute_query_to_dict(query, [payment_method])

            return [ORDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to filter OR list by payment method: {str(e)}", 500) from e

    def filter_by_date_range(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> list[ORDTO]:
        try:
            from datetime import datetime
            query = "SELECT * FROM treasurer_or_payment_summary()"
            rows = self._ctx.execute_query_to_dict(query, [])
            
            # Convert to list of DTOs
            result = [ORDTO(**row) for row in rows]
            
            # Apply filters
            if month is not None and year is not None:
                # Filter by specific month and year
                filtered = []
                for r in result:
                    if r.issued_at:
                        try:
                            # Check if it's already a datetime object
                            if isinstance(r.issued_at, datetime):
                                issued_dt = r.issued_at
                            elif isinstance(r.issued_at, str):
                                # Parse the datetime string
                                if 'T' in r.issued_at or ' ' in r.issued_at:
                                    issued_dt = datetime.fromisoformat(r.issued_at.replace('Z', '+00:00'))
                                else:
                                    issued_dt = datetime.strptime(r.issued_at, '%Y-%m-%d')
                            else:
                                continue
                            
                            if issued_dt.month == month and issued_dt.year == year:
                                filtered.append(r)
                        except (ValueError, AttributeError):
                            continue
                result = filtered
            elif month is not None:
                # Filter by month only (any year)
                filtered = []
                for r in result:
                    if r.issued_at:
                        try:
                            if isinstance(r.issued_at, datetime):
                                issued_dt = r.issued_at
                            elif isinstance(r.issued_at, str):
                                if 'T' in r.issued_at or ' ' in r.issued_at:
                                    issued_dt = datetime.fromisoformat(r.issued_at.replace('Z', '+00:00'))
                                else:
                                    issued_dt = datetime.strptime(r.issued_at, '%Y-%m-%d')
                            else:
                                continue
                            
                            if issued_dt.month == month:
                                filtered.append(r)
                        except (ValueError, AttributeError):
                            continue
                result = filtered
            elif year is not None:
                # Filter by year only
                filtered = []
                for r in result:
                    if r.issued_at:
                        try:
                            if isinstance(r.issued_at, datetime):
                                issued_dt = r.issued_at
                            elif isinstance(r.issued_at, str):
                                if 'T' in r.issued_at or ' ' in r.issued_at:
                                    issued_dt = datetime.fromisoformat(r.issued_at.replace('Z', '+00:00'))
                                else:
                                    issued_dt = datetime.strptime(r.issued_at, '%Y-%m-%d')
                            else:
                                continue
                            
                            if issued_dt.year == year:
                                filtered.append(r)
                        except (ValueError, AttributeError):
                            continue
                result = filtered
            elif date_from and date_to:
                # Filter by date range
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                filtered = []
                for r in result:
                    if r.issued_at:
                        try:
                            if isinstance(r.issued_at, datetime):
                                issued_dt = r.issued_at
                            elif isinstance(r.issued_at, str):
                                if 'T' in r.issued_at or ' ' in r.issued_at:
                                    issued_dt = datetime.fromisoformat(r.issued_at.replace('Z', '+00:00'))
                                else:
                                    issued_dt = datetime.strptime(r.issued_at, '%Y-%m-%d')
                            else:
                                continue
                            
                            if date_from_obj <= issued_dt.date() <= date_to_obj:
                                filtered.append(r)
                        except (ValueError, AttributeError):
                            continue
                result = filtered
            
            return result
        except Exception as e:
            raise QueryExecutionException(f"Failed to filter OR list by date range: {str(e)}", 500) from e