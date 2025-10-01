from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.app.transfer_objects.commands.reschedule_cmd import RescheduleCommand
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository


class SchedulingService(ISchedulingService):

    def __init__(self, scheduling_repository: ISchedulingRepository):
        self.scheduling_repository = scheduling_repository
        
    def execute_reschedule(self, week_start: str, reasoning: str, schedule_id: int, added_by: int) -> None:
        week_id = self.scheduling_repository.get_week_start_id_by_week_start_key(week_start=week_start)
        return self.scheduling_repository.insert_new_schedule(
            cmd=RescheduleCommand(
                p_schedule_id=schedule_id,
                p_new_week_id=week_id,
                p_resched_by_id=added_by,
                p_reason=reasoning,
            )
        )

    def execute(self, key=None, status=None, week_range=None) -> None:
        if key:
            return self.scheduling_repository.search_schedule(search_key=key)

        if status:
            return self.scheduling_repository.sort_by_status(status=status)
        
        if week_range:
            return self.scheduling_repository.sort_by_week_range(week_range=week_range)
        
        return self.scheduling_repository.fetch_schedules()
        