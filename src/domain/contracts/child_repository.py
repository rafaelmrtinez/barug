from abc import ABC, abstractmethod
from typing import Any


class IChildRepository(ABC):

    @abstractmethod
    def get_child_basic_info_by_person_id(self, id: int) -> Any:
        raise NotImplementedError()
