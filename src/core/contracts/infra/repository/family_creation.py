from abc import ABC, abstractmethod

class IFamilyCreationRepository(ABC):
    """
    Interface for family creation repository operations.
    Defines methods for creating and retrieving family unit data.
    """
    
    @abstractmethod
    def get_pending_request(self, requester_id: int) -> int:
        """
        Get the pending family creation request for the given requester ID.

        Args:
            requester_id (int): The ID of the requester.

        Returns:
            This will return a count of pending requests for the given requester ID.
        """
        pass

    @abstractmethod
    def create_family_unit(self, data: 'FamilyCreationPersistence') -> int:
        """
        Create a new family unit with the provided data.

        Args:
            data (dict): Data required to create a family unit.

        Returns:
            Any: Result of the creation operation.
        """
        pass

    @abstractmethod
    def get_all_family_count(self) -> int:
        """
        Retrieve the total count of all family units.

        Returns:
            int: Total number of family units.
        """
        pass

    @abstractmethod
    def get_family_count_by_household_id(self, id: str) -> int:
        """
        Get the count of family units associated with a specific household ID.

        Args:
            id (str): Household identifier.

        Returns:
            int: Number of family units for the given household.
        """
        pass

    @abstractmethod
    def get_resident_by_id(self, id: str) -> 'Resident':
        """
        Retrieve resident information by their ID.

        Args:
            id (str): Resident identifier.

        Returns:
            Resident: Resident object containing personal details.
        """
        pass

    @abstractmethod
    def get_household_info_by_house_num(self, house_num: str) -> 'HouseholdInformationDTO':
        """
        Get household information using the house number.

        Args:
            house_num (str): House number.

        Returns:
            dict: Household information.
        """
        pass

    @abstractmethod
    def find_resident_family_unit_if_exist(self, id: str) -> bool:
        """
        Check if a resident is already part of a family unit.

        Args:
            id (str): Resident identifier.

        Returns:
            bool: True if resident exists in a family unit, False otherwise.
        """
        pass