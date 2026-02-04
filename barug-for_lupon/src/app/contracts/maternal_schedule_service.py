from abc import ABC, abstractmethod
from typing import Optional


class IMaternalScheduleService(ABC):

    @abstractmethod
    def schedule_prenatal(self, mhr_id: int, date, time, staff_id: int, purpose: str, notes: Optional[str]):
        raise NotImplementedError()

    @abstractmethod
    def schedule_postpartum(self, mhr_id: int, date, time, staff_id: int, visit: str, purpose: str):
        raise NotImplementedError()
