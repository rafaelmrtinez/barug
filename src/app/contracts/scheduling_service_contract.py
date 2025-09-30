from abc import ABC, abstractmethod

class ISchedulingService(ABC):

    @abstractmethod
    def execute_reschedule(self, week_start: str, reasong: str):
        pass

    @abstractmethod
    def execute(self, key=None, status=None, week_range=None, year=None):
        pass