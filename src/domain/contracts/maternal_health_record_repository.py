from abc import ABC, abstractmethod
from typing import Any


class IMaternalHealthRecordRepository(ABC):

    @abstractmethod
    def fetch_anc_trimester_tracker_by_mhr_id(self, mhr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_all_delivery_plan(self) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_postpartum_record_bhw(self, *args, **kwargs) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_maternal_visit_schedule(self, mhr_id, date, time, staff_id, purpose, notes) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_postpartum_visit_schedule(self, mhr_id, date, time, staff_id, purpose, notes) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_latest_maternal_health_record_id_by_person_id(self, person_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_maternal_visit_and_schedule_completion(self, mhr_id, staff_id) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def update_maternal_record_status(self, mhr_id, status_id, staff_id) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_maternal_health_record_status_by_mhr_id(self, maternal_record_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_maternal_visit_statuses_by_mhr_id(self, mhr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_postpartum_visit_statuses_by_mhr_id(self, mhr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_latest_scheduled_visit_by_mhr_id(self, maternal_record_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_latest_prenatal_scheduled_by_mhr_id(self, maternal_record_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_latest_postpartum_scheduled_by_mhr_id(self, maternal_record_id: int) -> Any:
        raise NotImplementedError()
