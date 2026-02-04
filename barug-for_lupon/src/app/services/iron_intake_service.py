from __future__ import annotations

from typing import Optional, Dict

from src.app.contracts.iron_intake_service import IIronIntakeService
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.services.iron_intake_domain_service import IronIntakeDomainService
from src.domain.exceptions.iron_intake_domain_exception import IronIntakeDomainException


class IronIntakeService(IIronIntakeService):
    def __init__(self, ch_repo: IChildHealthRecordRepository, domain_service: IronIntakeDomainService):
        self.ch_repo = ch_repo
        self.domain_service = domain_service

    def insert_iron_intake(
        self,
        child_record_id: int,
        assessed_by_id: int,
        date_started: str | None,
        date_completed: str | None,
    ) -> Optional[Dict]:
        # Delegate validation and normalization to domain service
        payload = {
            "date_started": date_started,
            "date_completed": date_completed,
        }
        try:
            normalized = self.domain_service.validate_and_prepare(child_record_id, payload)
        except IronIntakeDomainException:
            # let API handle domain exceptions
            raise

        try:
            # pass date objects to repository (strong typing)
            return self.ch_repo.upsert_iron_supplement_completion_by_chr_id(
                chr_id=child_record_id,
                assessed_by_id=assessed_by_id,
                date_started=normalized.get("date_started"),
                date_completed=normalized.get("date_completed"),
            )
        except ChildHealthRecordException:
            raise
