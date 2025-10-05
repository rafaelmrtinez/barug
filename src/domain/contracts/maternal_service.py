from abc import ABC, abstractmethod

class IMaternalService(ABC):
    
    @abstractmethod
    def execute_child_visit(self, visit_data, person_id: int):
        pass

    @abstractmethod
    def execute_insert_child_record(self, child_data) -> int:
        pass