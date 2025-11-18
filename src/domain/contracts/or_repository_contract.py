from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)

class IORRepository(ABC):

    @abstractmethod
    def fetch_or_list(self) -> list[ORDTO]:
        pass

