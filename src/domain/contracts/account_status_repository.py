from abc import ABC, abstractmethod
from typing import Any


class IAccountStatusRepository(ABC):

    @abstractmethod
    def get_all(self) -> Any:
        """Return all account/request statuses."""
        raise NotImplementedError()
