from abc import ABC, abstractmethod


class IFamilyMembershipRepository(ABC):
    
    """Interface for family membership repository.
    """
    
    @abstractmethod
    def join_family_unit(self, data) -> str:
        pass
        
    @abstractmethod
    def get_family_unit_id(self, id: str) -> bool:
        pass

    @abstractmethod
    def get_household_active_status(self, id: str) -> bool:
        pass
    
    @abstractmethod    
    def get_resident_id(self, id: str) -> str:
        pass