from abc import ABC, abstractmethod
from typing import Optional
from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
    ResidentDetailDTO,
)

class IResidentRepository(ABC):
    
    @abstractmethod
    def fetch_resident_list(self) -> list[ResidetDTO]:
        pass

    @abstractmethod
    def search_resident(self, search: str) -> list[ResidetDTO]:
        pass

    @abstractmethod
    def sort_purok(self, purok: int) -> list[ResidetDTO]:
        pass

    @abstractmethod
    def fetch_resident_detail(self, person_id: int) -> Optional[ResidentDetailDTO]:
        pass 