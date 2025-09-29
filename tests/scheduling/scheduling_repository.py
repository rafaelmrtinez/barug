from unittest import TestCase
from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository

class SchedulingRepositoryTest(TestCase):
    
    def setUp(self):
        self.repo: ActiveScheduleRepository = ActiveScheduleRepository(ConnectionAdapter())
        
    def test_sort_by_week_range(self):
        key = "Week of Jul 07 – Jul 11"
        year = "2025"
        print(self.repo.sort_by_week_range(week_range=key, year=year))

    def test_search_schedule(self):
        key = "hannah"
        
    def test_fetch_schedules(self):
        result = self.repo.fetch_schedules()
            