from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository


class SchedulingService(ISchedulingService):

    def __init__(self, scheduling_repository: ISchedulingRepository):
        self.scheduling_repository = scheduling_repository

    def get_active_schedules(self):
        return self.scheduling_repository.fetch_schedules()