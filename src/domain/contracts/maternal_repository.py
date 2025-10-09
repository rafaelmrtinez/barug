from abc import abstractmethod, ABC

class IMaternalRepository(ABC):
    
    @abstractmethod
    def fetch_maternal_record_history_by_maternal_record_id(self, id: int):
        pass
    
    @abstractmethod
    def fetch_current_maternal_record_by_maternal_visit_id(self, id: int):
        pass
    
    @abstractmethod
    def fetch_previous_maternal_record_by_maternal_visit_id(self, id: int):
        pass
    
    @abstractmethod
    def fetch_family_number_by_person_id(self, id: int) -> int | None:
        pass
    
    @abstractmethod
    def fetch_immunization_stage_by_child_health_record_id(self, child_health_record_id: int) -> str:
        pass
    
    @abstractmethod
    def fetch_immunization_type_id_by_type_name(self, immunization_type_name: str) -> int:
        pass

    @abstractmethod
    def fetch_child_record_by_person_id(self, person_id: int) -> list[dict]:
        pass

    @abstractmethod
    def insert_child_visit(self, data):
        pass

    @abstractmethod
    def insert_child_record(self, request) -> int:
        pass