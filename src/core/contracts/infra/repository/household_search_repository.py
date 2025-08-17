from abc import ABC, abstractmethod


class IHouseholdSearchRepository(ABC):

    """
    Interface for household repository
    """

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