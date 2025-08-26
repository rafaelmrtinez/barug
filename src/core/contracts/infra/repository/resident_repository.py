from abc import ABC, abstractmethod


class IResidentRepository(ABC):
    
    @abstractmethod
    def get_resident_by_id(self, id: str) -> "Resident":
        pass