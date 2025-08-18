from abc import ABC, abstractmethod
from typing import Any


class IService(ABC):

    """This is a base interface for all services"""

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """This method is used to execute and perform orchestration
        at the application level to different repositories and domain
        to enforce business rules and CRUD operations.

        Args:
            **kwargs: Arbitrary keyword arguments containing the necessary data
            for the orchestration process.

        Returns:
            bool: True if the orchestration was successful, False otherwise.
        """
        pass