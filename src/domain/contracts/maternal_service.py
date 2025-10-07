from abc import ABC, abstractmethod

class IMaternalService(ABC):

    @abstractmethod
    def insert_child_record(self, child_data) -> int:
        pass