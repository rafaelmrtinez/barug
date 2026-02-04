from abc import ABC, abstractmethod

class IFamilyRepository(ABC):
    
    @abstractmethod
    def get_family_id_by_family_no(self, family_no: str) -> int:
        pass