from abc import abstractmethod, ABC

class IMaternalRepository(ABC):

    @abstractmethod
    def get_child_record_by_person_id(self, person_id: int) -> list[dict]:
        pass

    @abstractmethod
    def insert_child_visit(self, data):
        pass

    @abstractmethod
    def insert_child_record(self, request) -> int:
        pass