from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict


class IBirthSupplementationService(ABC):
    @abstractmethod
    def insert_birth_supplementation(
        self,
        child_record_id: int,
        assessed_by_id: int,
        date_assessed: str | None,
        anemic_seen: str | None,
        anemic_given_iron: str | None,
        birth_weight: str | None,
        is_low_birth_weight: bool | None,
        seen_2_6_mos: str | None,
        given_2_6_mos: str | None,
        tt_status: int | None,
    ) -> Optional[Dict]:
        """Insert or orchestrate birth & supplementation data for a child record.

        Returns a dict-like result from repository on success, or None.
        """
        raise NotImplementedError()
