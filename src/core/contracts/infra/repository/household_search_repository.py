from abc import ABC, abstractmethod


class IHouseholdSearchRepository(ABC):

    """
    Interface for household repository
    """
    
    @abstractmethod
    def get(self, household_id) -> dict:
        """This method will get the family data and address information
        by household ID.

        Args:
            household_id: The ID of the household to retrieve data for.

        Returns:
            dict: A dictionary containing family data and address data.
        """
        pass

    @abstractmethod
    def find(self, key: str) -> dict:
        """This method will find every household information by household number or head.

        Args:
            key (str): The household number or head to search for.

        Returns:
            dict: The return data will consist of
            - Household Head Full Name (str)
            - Household Number (str)
            - Active Status (boolean)
        """
        pass