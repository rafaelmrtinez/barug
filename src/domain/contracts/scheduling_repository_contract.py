from abc import ABC, abstractmethod

from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO

class ISchedulingRepository(ABC):
    
    @abstractmethod
    def insert_new_schedule(self, cmd: "RescheduleCommand") -> list[dict] | None:
        pass
    
    @abstractmethod
    def get_week_start_id_by_week_start_key(self, week_start: str)-> list[dict]:
        pass

    @abstractmethod
    def sort_by_status(self, status: str) -> list[ActiveScheduleDTO]:
        pass
        
    @abstractmethod
    def search_schedule(self, search_key: str) -> list[ActiveScheduleDTO]:
        pass
    
    @abstractmethod
    def sort_by_week_range(self, week_range: str, year: str) -> list[ActiveScheduleDTO]:
        pass
        
    @abstractmethod
    def fetch_schedules(self) -> list[ActiveScheduleDTO]:
        pass