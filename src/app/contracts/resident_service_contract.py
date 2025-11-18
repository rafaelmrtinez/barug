from abc import ABC, abstractmethod
from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
)

class IResidentService(ABC):
    @abstractmethod
    def execute(
        self,
        search: str | None,
        purok: int | None,
    ) -> list[ResidetDTO]:
        pass