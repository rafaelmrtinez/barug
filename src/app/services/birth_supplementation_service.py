from __future__ import annotations

from typing import Optional, Dict

from src.app.contracts.birth_supplementation_service import IBirthSupplementationService
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.domain.services.birth_supplementation_domain_service import BirthSupplementationDomainService
from src.domain.exceptions.birth_supplementation_domain_exception import BirthSupplementationDomainException


class BirthSupplementationService(IBirthSupplementationService):
    def __init__(self, ch_repo: IChildHealthRecordRepository, domain_service: BirthSupplementationDomainService):
        self.ch_repo = ch_repo
        self.domain_service = domain_service

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
        # Delegate validation and normalization to domain service
        payload = {
            "date_assessed": date_assessed,
            "anemic_seen": anemic_seen,
            "anemic_given_iron": anemic_given_iron,
            "birth_weight": birth_weight,
            "is_low_birth_weight": is_low_birth_weight,
            "seen_2_6_mos": seen_2_6_mos,
            "given_2_6_mos": given_2_6_mos,
            "tt_status": tt_status,
        }
        try:
            normalized = self.domain_service.validate_and_prepare(payload)
        except BirthSupplementationDomainException:
            # Let API layer handle domain errors
            raise

        try:
            return self.ch_repo.insert_child_screening(
                chr_id=child_record_id,
                assessed_by_id=assessed_by_id,
                date_assessed=normalized.get("date_assessed"),
                anemic_seen=normalized.get("anemic_seen") or normalized.get("anemia_2_59_seen"),
                anemic_given_iron=normalized.get("anemic_given_iron") or normalized.get("anemia_2_59_given_iron"),
                birth_weight=normalized.get("birth_weight"),
                is_low_birth_weight=normalized.get("is_low_birth_weight"),
                seen_2_6_mos=normalized.get("seen_2_6_mos"),
                given_2_6_mos=normalized.get("given_2_6_mos"),
                tt_status=normalized.get("tt_status"),
            )
        except ChildHealthRecordException:
            raise
