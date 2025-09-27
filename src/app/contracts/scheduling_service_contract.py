from abc import ABC, abstractmethod

class ISchedulingService(ABC):

    @abstractmethod
    def get_active_schedules(self):
        pass