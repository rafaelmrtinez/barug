from abc import ABC, abstractmethod


class IChildRepository(ABC):

    @abstractmethod
    def get_child_basic_info_by_person_id(self, id: int):
        pass