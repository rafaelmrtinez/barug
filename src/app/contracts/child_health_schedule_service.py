from abc import ABC, abstractmethod
from typing import Optional

from src.app.transfer_objects.request.visit_schedule_request import VisitScheduleRequest


class IChildHealthScheduleService(ABC):
    """Contract for child health schedule service implementations.

    Implementations should provide create_visit_schedule which accepts a
    VisitScheduleRequest and the id of the staff who created it.
    """

    @abstractmethod
    def create_visit_schedule(self, dto: VisitScheduleRequest, created_by_id: int) -> Optional[list]:
        raise NotImplementedError()
