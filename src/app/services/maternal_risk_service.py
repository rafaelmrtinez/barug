import logging
from typing import Any, List

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

logger = logging.getLogger(__name__)


class MaternalRiskService:
    """Service to validate and persist risk codes for a maternal health record.

    Responsibilities:
      - validate incoming payload
      - coerce/normalize values (ensure list of ints for risk categories)
      - delegate persistence to the repository
      - raise MaternalHealthRecordException for domain/validation errors
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repo = repository

    def _normalize_categories(self, categories: Any) -> List[int]:
        if categories is None:
            return []
        if isinstance(categories, list):
            out = []
            for v in categories:
                try:
                    out.append(int(v))
                except Exception:
                    raise MaternalHealthRecordException("Invalid risk category id provided; must be integers.")
            return out
        # If categories provided as a comma separated string
        if isinstance(categories, str):
            if categories.strip() == "":
                return []
            parts = [p.strip() for p in categories.split(',') if p.strip()]
            out = []
            for p in parts:
                try:
                    out.append(int(p))
                except Exception:
                    raise MaternalHealthRecordException("Invalid risk category id provided; must be integers.")
            return out
        raise MaternalHealthRecordException("Invalid risk categories payload; expected list of integers.")

    def insert_risk_codes(self, maternal_record_id: int, assessed_by_id: int, risk_categories: Any):
        """Validate and persist risk categories for a maternal health record.

        Returns repository result on success.
        """
        try:
            mhr_id = int(maternal_record_id)
            if mhr_id <= 0:
                raise ValueError()
        except Exception:
            raise MaternalHealthRecordException("Invalid maternal health record id.")

        try:
            assessed_by = int(assessed_by_id)
            # if assessed_by <= 0:
            #     raise ValueError()
        except Exception:
            raise MaternalHealthRecordException("Invalid assessed_by id.")

        categories = self._normalize_categories(risk_categories)

        # Delegate to repository. Repository will convert to Json/JSONB.
        try:
            return self.repo.insert_risk_codes(p_maternal_health_record_id=mhr_id,
                                              p_assessed_by_id=assessed_by,
                                              p_risk_categories=categories)
        except MaternalHealthRecordException:
            # propagate domain exceptions
            raise
        except Exception as e:
            logger.exception("Unexpected error while inserting risk codes for mhr_id=%s", mhr_id)
            raise
