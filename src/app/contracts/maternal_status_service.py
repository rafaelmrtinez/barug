from abc import ABC, abstractmethod


class IMaternalRecordStatusService(ABC):

    @abstractmethod
    def is_valid_status(self, status_id: int) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def update_status(self, mhr_id: int, status_id: int, staff_id: int):
        raise NotImplementedError()
