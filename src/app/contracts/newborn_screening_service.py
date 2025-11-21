from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict


class INewbornScreeningService(ABC):
    @abstractmethod
    def insert_newborn_screening(
        self,
        child_record_id: int,
        assessed_by_id: int,
        feeding_type_id: int | None,
        referred_nbs_date: str | None,
    ) -> Optional[Dict]:
        """Insert or orchestrate newborn screening data for a child record.

        Returns a dict-like result from repository on success, or None.
        """
        raise NotImplementedError()
