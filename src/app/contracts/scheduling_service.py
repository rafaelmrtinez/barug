from abc import ABC, abstractmethod
from typing import Any, Optional


class ISchedulingService(ABC):

    @abstractmethod
    def execute_reschedule(self, week_start: str, reasoning: str, schedule_id: int, added_by: int) -> None:
        raise NotImplementedError()

    @abstractmethod
    def execute(self, key: Optional[str] = None, status: Optional[Any] = None, week_range: Optional[Any] = None) -> Any:
        raise NotImplementedError()
