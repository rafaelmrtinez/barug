from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
)
from src.app.contracts.resident_service_contract import (
    IResidentRepository,
)
from src.domain.contracts.resident_repository_contract import (
    IResidentRepository,
)

class ResidentService(IResidentRepository):
    def __init__(
        self,
        resident_repository: IResidentRepository,
    ):
        self._resident_repo = resident_repository

    def execute(
        self,
        search: str | None = None,
        purok: int | None = None,
    ) -> list[ResidetDTO]:
        if search:
            return self._resident_repo.search_resident(search)
        if purok is not None:
            return self._resident_repo.sort_purok(purok)
        
        return self._resident_repo.fetch_resident_list()
