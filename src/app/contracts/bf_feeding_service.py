from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class IBFFeedingService(ABC):
    @abstractmethod
    def process_and_insert(self, chr_id: int, staff_id: int, payload: Dict[str, Any]) -> Any:
        """Validate payload and insert breastfeeding check. Returns repository result or raises on error."""
        raise NotImplementedError()
