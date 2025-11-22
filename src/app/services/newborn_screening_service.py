from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional, Dict

from src.app.contracts.newborn_screening_service import INewbornScreeningService
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.domain.services.newborn_screening_domain_service import NewbornScreeningDomainService
from src.domain.exceptions.newborn_screening_domain_exception import NewbornScreeningDomainException

logger = logging.getLogger(__name__)


class NewbornScreeningService(INewbornScreeningService):
    def __init__(self, ch_repo: IChildHealthRecordRepository, domain_service: NewbornScreeningDomainService):
        self.ch_repo = ch_repo
        self.domain_service = domain_service

    def insert_newborn_screening(
        self,
        child_record_id: int,
        assessed_by_id: int,
        feeding_type_id: int | None,
        referred_nbs_date: str | None,
    ) -> Optional[Dict]:
        # Delegate business rules/validation to domain service which
        # will return normalized feeding_type_id and ISO date string or None
        try:
            ft_id, iso_date = self.domain_service.validate_and_prepare(
                child_record_id=child_record_id,
                feeding_type_id=feeding_type_id,
                referred_nbs_date_raw=referred_nbs_date,
            )
            return self.ch_repo.insert_new_born_screening_date(
                p_child_record_id=child_record_id,
                p_assessed_by_id=assessed_by_id,
                feeding_type_id=ft_id,
                p_referred_nbs_date=iso_date,
            )
        except ChildHealthRecordException:
            # re-raise domain-specific exceptions for upper layers to handle
            raise
        except NewbornScreeningDomainException:
            # bubble domain validation errors up for the API layer to handle
            raise
        except Exception as e:
            logger.exception("Failed to insert newborn screening: %s", e)
            raise
