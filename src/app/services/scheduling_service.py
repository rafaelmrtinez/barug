from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository


class SchedulingService(ISchedulingService):

    def __init__(self, scheduling_repository: ISchedulingRepository):
        self.scheduling_repository = scheduling_repository

    def execute(self, key=None, status=None, week_range=None) -> None:
        if key:
            return self.scheduling_repository.search_schedule(search_key=key)

        if status:
            return self.scheduling_repository.sort_by_status(status=status)
        
        if week_range:
            return self.scheduling_repository.sort_by_week_range(week_range=week_range)
        
        return self.scheduling_repository.fetch_schedules()
        