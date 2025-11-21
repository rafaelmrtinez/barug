from __future__ import annotations

from typing import Optional, Dict, Any
from decimal import Decimal

from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.exceptions.birth_supplementation_domain_exception import BirthSupplementationDomainException
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository


class BirthSupplementationDomainService:
    """Business rules for Birth & Supplementation.

    Rules implemented:
    - `date_assessed` must not be in the future (Manila timezone).
    - `birth_weight` must be appropriate; low birth weight (< 2.5 kg) flagged.
    - If `anemic_seen` is not provided (None/falsey), `anemic_given_iron` must not be provided.
    - If `seen_2_6_mos` is not provided, `given_2_6_mos` must not be provided.
    - Any date fields must not be in the future.
    - Automatically set `is_low_birth_weight` to True when `birth_weight` < 2.5 kg.
    """

    LOW_BIRTH_WEIGHT_THRESHOLD_KG = Decimal("2.5")

    def __init__(self, ch_repo: IChildHealthRecordRepository):
        self.ch_repo = ch_repo

    def validate_and_prepare(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # copy to avoid mutating caller's dict
        data = dict(payload or {})

        # Normalize and parse dates
        date_assessed = data.get("date_assessed") or data.get("data_assessed")
        if date_assessed:
            parsed = DateAndTimeUtility.parse_date(date_assessed)
            if not parsed:
                raise BirthSupplementationDomainException("Invalid date format for date_assessed. Use YYYY-MM-DD")
            if parsed > DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()):
                raise BirthSupplementationDomainException("date_assessed cannot be in the future")
            data["date_assessed"] = parsed.isoformat()

        # birth weight logic
        bw = data.get("birth_weight")
        if bw is not None and bw != "":
            try:
                # allow strings like '2.5' or numeric
                bw_decimal = Decimal(str(bw))
            except Exception:
                raise BirthSupplementationDomainException("Invalid birth_weight format; expected numeric value in kilograms")
            # automatically set low birth weight if below threshold
            if bw_decimal < self.LOW_BIRTH_WEIGHT_THRESHOLD_KG:
                data["is_low_birth_weight"] = True
            # store normalized string
            data["birth_weight"] = str(bw_decimal)

        # Anemic rules for 2-59 mos
        anemic_seen = data.get("anemic_seen") or data.get("anemia_2_59_seen")
        anemic_given = data.get("anemic_given_iron") or data.get("anemia_2_59_given_iron")
        if (anemic_given or anemic_given == True) and not anemic_seen:
            raise BirthSupplementationDomainException("Cannot record 'given iron' for anemic children when 'anemic seen' is not provided")

        # 2-6 months rules
        seen_2_6 = data.get("seen_2_6_mos") or data.get("birth_wt_seen")
        given_2_6 = data.get("given_2_6_mos") or data.get("birth_wt_given_iron")
        if (given_2_6 or given_2_6 == True) and not seen_2_6:
            raise BirthSupplementationDomainException("Cannot record 'given iron for 2-6 months' when 'seen 2-6 months' is not provided")

        # guard against future dates in other date fields if present
        date_fields = ["seen_2_6_mos", "given_2_6_mos"]
        for key in date_fields:
            val = data.get(key)
            if val:
                parsed = DateAndTimeUtility.parse_date(val)
                if not parsed:
                    raise BirthSupplementationDomainException(f"Invalid date format for {key}; use YYYY-MM-DD")
                if parsed > DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()):
                    raise BirthSupplementationDomainException(f"{key} cannot be set in the future")
                data[key] = parsed.isoformat()

        return data
