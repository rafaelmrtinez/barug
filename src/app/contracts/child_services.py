from abc import ABC, abstractmethod


class IChildService(ABC):

    @abstractmethod
    def execute_get_child_basic_info(self, id: int):
        pass