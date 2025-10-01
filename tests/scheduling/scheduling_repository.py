from unittest import TestCase
from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository

class SchedulingRepositoryTest(TestCase):
    
    def setUp(self):
        self.repo: ActiveScheduleRepository = ActiveScheduleRepository(ConnectionAdapter())

    def test_insert_new_schedule(self):
        from src.app.transfer_objects.commands.reschedule_cmd import RescheduleCommand
        cmd = RescheduleCommand(
            p_schedule_id=12,
            p_new_week_id=2,
            p_reason="Testing",
            p_resched_by_id=1
        )
        print(self.repo.insert_new_schedule(cmd))