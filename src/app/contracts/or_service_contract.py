from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from src.app.transfer_objects.dto.or_dto import (
    ORDTO,
)

class IORService(ABC):

    @abstractmethod
    def execute(
        self,
    ) -> list[ORDTO]:
        """
        Returns:
          rows:    filtered OR rows
        """
        pass