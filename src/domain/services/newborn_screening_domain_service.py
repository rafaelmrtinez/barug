from __future__ import annotations

from typing import Optional, Tuple
from datetime import datetime

from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.domain.exceptions.newborn_screening_domain_exception import NewbornScreeningDomainException


class NewbornScreeningDomainService:
    """Domain service that enforces business rules for newborn screening.

    Rules implemented:
    - referred date must be today or a past date (Manila timezone)
    - only a valid feeding_type_id is accepted
    - only one newborn screening record may exist per child record
    """

    def __init__(self, ch_repo: IChildHealthRecordRepository):
        self.ch_repo = ch_repo

    def validate_and_prepare(
        self,
        child_record_id: int,
        feeding_type_id: Optional[int] | None,
        referred_nbs_date_raw: Optional[str] | None,
    ) -> Tuple[Optional[int], Optional[str]]:
        # parse date using infra utility (Manila timezone-aware current date)
        parsed_date = DateAndTimeUtility.parse_date(referred_nbs_date_raw) if referred_nbs_date_raw else None

        # verify date is not in the future (compare using Manila current date)
        today_str = DateAndTimeUtility.get_current_date()
        try:
            today = datetime.strptime(today_str, "%Y-%m-%d").date()
        except Exception:
            raise NewbornScreeningDomainException("Unable to determine current date")

        if parsed_date is not None and parsed_date > today:
            raise NewbornScreeningDomainException("Referred newborn screening date cannot be in the future")

        # validate feeding type id if present
        if feeding_type_id is not None and feeding_type_id != "":
            try:
                ft_id = int(feeding_type_id)
            except Exception:
                raise NewbornScreeningDomainException("Invalid feeding type id")
            # check against available feeding types
            available = self.ch_repo.fetch_all_feeding_type_dict() or []
            allowed_ids = {int(r.get("feeding_type_id")) for r in available if r.get("feeding_type_id") is not None}
            if ft_id not in allowed_ids:
                raise NewbornScreeningDomainException("Feeding type is not allowed")
        else:
            raise NewbornScreeningDomainException("Feeding type is required")

        # ensure only one record exists for this child
        existing = self.ch_repo.fetch_new_born_screening_date_by_chr_id(child_record_id)
        if existing:
            raise NewbornScreeningDomainException("A newborn screening record already exists for this child")

        # return normalized values; repository expects date or None, and int or None
        return ft_id, (parsed_date.isoformat() if parsed_date is not None else None)
