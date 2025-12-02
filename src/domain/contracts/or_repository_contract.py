from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)

class IORRepository(ABC):

    @abstractmethod
    def fetch_or_list(self) -> list[ORDTO]:
        pass

    @abstractmethod
    def search_or_list(self, search: str) -> list[ORDTO]:
        pass

    @abstractmethod
    def filter_by_payment_method(self, payment_method: int) -> list[ORDTO]:
        pass

    @abstractmethod
    def filter_by_date_range(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> list[ORDTO]:
        pass
