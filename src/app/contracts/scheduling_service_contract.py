from abc import ABC, abstractmethod

class ISchedulingService(ABC):

    @abstractmethod
    def execute(self, key=None, status=None, week_range=None, year=None):
        pass