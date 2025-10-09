from abc import ABC, abstractmethod

class IMaternalService(ABC):
    
    @abstractmethod
    def execute_fetch_maternal_for_new_child(self, person_record_id: int):
        pass
    
    @abstractmethod
    def execute_fetch_maternal_record(self, person_id: int):
        pass
    
    @abstractmethod
    def execute_child_visit(self, visit_data, immunization_data):
        pass

    @abstractmethod
    def execute_insert_child_record(self, child_data) -> int:
        pass