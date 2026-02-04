from abc import ABC, abstractmethod
from typing import Any


class IWeekRangeRepository(ABC):

    @abstractmethod
    def get_all(self) -> Any:
        raise NotImplementedError()
