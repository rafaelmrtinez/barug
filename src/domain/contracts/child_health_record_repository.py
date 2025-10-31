from abc import ABC, abstractmethod
from typing import Any


class IChildHealthRecordRepository(ABC):
    @abstractmethod
    def fetch_all_tt_types(self) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_vitamin_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def upsert_vitamin_a_stage_by_chr_id(self, p_child_record_id: int, staff_id: int, stage_id: int, date_given) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_iron_supplement_completion_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def upsert_iron_supplement_completion_by_chr_id(self, chr_id: int, assessed_by_id: int, date_started, date_completed) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_mother_tt_type(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_child_screening(self, *args, **kwargs) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_child_monitoring_log(self, log, chr_id: int, staff_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_new_born_screening_date_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_new_born_screening_date(self, p_child_record_id, p_assessed_by_id, p_referred_nbs_date, feeding_type_id) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_immunization_dates_matrix_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_child_immunizations(self, p_child_record_id, p_assessed_by_id, p_immunization_type_id, p_immunization_stage_given_id, p_date_given) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_child_details_bf_display_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def insert_bf_check(self, p_child_record_id, p_assessed_by_id, p_check_date) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_child_health_record_info_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_all_basic_chr_record(self) -> Any:
        raise NotImplementedError()
