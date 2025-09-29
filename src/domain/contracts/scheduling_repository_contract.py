from abc import ABC, abstractmethod

from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO

class ISchedulingRepository(ABC):

    def sort_by_status(self, status: str) -> list[ActiveScheduleDTO]:
        pass
        
    def search_schedule(self, search_key: str) -> list[ActiveScheduleDTO]:
        pass
    
    def sort_by_week_range(self, week_range: str, year: str) -> list[ActiveScheduleDTO]:
        pass
        
    def fetch_schedules(self) -> list[ActiveScheduleDTO]:
        pass