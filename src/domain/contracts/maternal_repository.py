from abc import abstractmethod, ABC

class IMaternalRepository(ABC):
    
    @abstractmethod
    def insert_child_record(self, request) -> int:
        pass