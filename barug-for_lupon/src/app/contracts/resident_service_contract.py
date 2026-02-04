from abc import ABC, abstractmethod
from typing import Optional
from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
    ResidentDetailDTO,
)

class IResidentService(ABC):
    @abstractmethod
    def execute(
        self,
        search: str | None,
        purok: int | None,
    ) -> list[ResidetDTO]:
        pass

    @abstractmethod
    def get_resident_detail(self, person_id: int) -> Optional[ResidentDetailDTO]:
        pass