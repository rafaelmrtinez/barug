from abc import abstractmethod, ABC

class IMaternalRepository(ABC):
    
    @abstractmethod
    def get_immunization_stage_by_child_health_record_id(self, child_health_record_id: int) -> str:
        pass
    
    @abstractmethod
    def get_immunization_type_id_by_type_name(self, immunization_type_name: str) -> int:
        pass

    @abstractmethod
    def get_child_record_by_person_id(self, person_id: int) -> list[dict]:
        pass

    @abstractmethod
    def insert_child_visit(self, data):
        pass

    @abstractmethod
    def insert_child_record(self, request) -> int:
        pass