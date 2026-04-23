from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class IMaternalPostpartumService(ABC):

    @abstractmethod
    def insert_postpartum_record(self, payload: Dict[str, Any], added_by_id: int, attended_by_role_name: Optional[str] = None):
        """Validate and insert a postpartum record."""
        raise NotImplementedError()
