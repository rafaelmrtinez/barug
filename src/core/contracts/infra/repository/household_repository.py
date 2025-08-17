from abc import ABC, abstractmethod


class IHouseholdRepository(ABC):

    """
    Interface for household repository
    """

    @abstractmethod
    def find_household_by_household_number(self, household_number: str) -> dict:
        """This method is used to search for household information to be used
        for search.
        Args:
            household_number (str): The household number to search for.
        """
        pass
    
    @abstractmethod
    def find_household_by_household_head(self, head: str) -> dict:
        """This method is used to search for household information by household head.
        Args:
            head (str): The name of the household head to search for.
        """
        pass