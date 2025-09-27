from abc import ABC, abstractmethod

class ISchedulingRepository(ABC):

    @abstractmethod
    def fetch_schedules(self):
        pass