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
    ) -> list[ORDTO]:
        return self._or_repo.fetch_or_list()