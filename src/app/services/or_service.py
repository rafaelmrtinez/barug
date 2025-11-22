from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)
from src.app.contracts.or_service_contract import (
    IORService,
)
from src.domain.contracts.or_repository_contract import (
    IORRepository,
)

class ORService(IORService):
    def __init__(
        self,
        or_repository: IORRepository,
    ):
        self._or_repo = or_repository

    def execute(
        self,
        search: str = None,
        payment_method: int = None
    ) -> list[ORDTO]:
        if search:
            return self._or_repo.search_or_list(search)
        if payment_method is not None:
            return self._or_repo.filter_by_payment_method(payment_method)
        
        return self._or_repo.fetch_or_list()