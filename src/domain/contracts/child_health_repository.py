from abc import ABC, abstractmethod
from typing import Any


class IChildHealthRepository(ABC):

    @abstractmethod
    def insert_child_immunizations(self, immunization) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_immunization_stages_by_chr_id_and_visit_id(self, chr_id: int) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetch_recent_visit_id_by_chr_id(self, chr_id: int) -> Any:
        raise NotImplementedError()
