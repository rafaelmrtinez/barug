from unittest import TestCase
from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.scheduling_repository import SchedulingRepository

class SchedulingRepositoryTest(TestCase):
    
    def setUp(self):
        self.repo: SchedulingRepository = SchedulingRepository(ConnectionAdapter())
        
    def test_fetch_schedules(self):
        result = self.repo.fetch_schedules()
        obj = []
        for row in result:
            obj.append(ActiveScheduleDTO(*row))
        self.assertIsInstance(obj, list)
        self.assertIsInstance(obj[0], ActiveScheduleDTO)
            