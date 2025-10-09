from abc import ABC, abstractmethod


class IChildRepository(ABC):

    @abstractmethod
    def fetch_child_health_record_by_person_id(self, id: int) -> int:
        pass

    @abstractmethod
    def get_child_basic_info_by_person_id(self, id: int):
        pass