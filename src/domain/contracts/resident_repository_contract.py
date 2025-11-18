from abc import ABC, abstractmethod
from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
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