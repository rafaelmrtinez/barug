from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict


class IIronIntakeService(ABC):
    @abstractmethod
    def insert_iron_intake(
        self,
        child_record_id: int,
        assessed_by_id: int,
        date_started: str | None,
        date_completed: str | None,
    ) -> Optional[Dict]:
        """Insert or orchestrate iron intake/iron supplement completion data."""
        raise NotImplementedError()
