from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)
from src.app.contracts.or_service_contract import (
    IORService,
)
from src.domain.contracts.or_repository_contract import (
    IORRepository,
)
from typing import Optional

class ORService(IORService):
    def __init__(
        self,
        or_repository: IORRepository,
    ):
        self._or_repo = or_repository

    def execute(
        self,
        search: Optional[str] = None,
        payment_method: Optional[int] = None,
        month: Optional[int] = None,
        year: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> list[ORDTO]:
        # Priority: search > payment_method > date filters > all
        if search:
            return self._or_repo.search_or_list(search)
        if payment_method is not None:
            return self._or_repo.filter_by_payment_method(payment_method)
        if month or year or date_from or date_to:
            return self._or_repo.filter_by_date_range(
                month=month,
                year=year,
                date_from=date_from,
                date_to=date_to
            )
        
        return self._or_repo.fetch_or_list()