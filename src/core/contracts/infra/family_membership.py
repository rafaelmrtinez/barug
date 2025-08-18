from abc import ABC, abstractmethod


class IFamilyMembershipRepository(ABC):
    
    """Interface for family membership repository.
    """
    
    @abstractmethod
    def find_resident(self, id: int) -> int:
        """Searched every household if a resident already a member or not"""
        pass
    
    @abstractmethod
    def insert_membership(self, data) -> str:
        """Join a resident to a family unit via sql function."""
        pass
    
    @abstractmethod
    def get_family_unit_status(self, id: int) -> bool:
        """Retrieves the family unit data for a given ID."""
        pass
        
    @abstractmethod
    def get_household_status(self, id: int) -> bool:
        """Fetches the household data for a given ID."""
        pass
    
    @abstractmethod
    def get_resident_basic_info(self, id: int) -> set:
        """Retrieves basic information about a resident by their ID.

        Args:
            id (int): The ID of the resident.

        Returns:
            set: {
                "person_id": int,
                "residential_status_id": int,
                "person_status_id": int
            }
        """
        pass