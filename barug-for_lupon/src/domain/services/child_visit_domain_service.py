import logging
from decimal import Decimal
from typing import Any, Dict

from src.infra.utilities.validation_utils import ValidationUtils
from src.infra.utilities.message_catalog import MessageCatalog
from src.domain.exceptions.child_visit_domain_exception import ChildVisitDomainException

logger = logging.getLogger(__name__)


class ChildVisitDomainService:
    """Domain validation for child visit (child monitoring log).

    Enforces business rules:
    - age < 5
    - allow float age for infants under 1 year
    - weight between reasonable min/max
    - temperature within human limits
    - height in centimeters within reasonable limits
    - findings required
    - notes optional
    - no emoji in text fields
    """

    MIN_WEIGHT = Decimal("0.5")
    MAX_WEIGHT = Decimal("40")
    MIN_TEMP = Decimal("34.0")
    MAX_TEMP = Decimal("42.0")
    MIN_HEIGHT = Decimal("30")
    MAX_HEIGHT = Decimal("150")

    def __init__(self, ch_repo=None, child_monitoring_query=None):
        # Accept repository dependency for future use (not required now)
        self._repo = ch_repo
        # optional query helper to read existing monitoring rows
        self._monitoring_query = child_monitoring_query

    def validate_and_normalize(self, payload: Dict[str, Any], role: str | None = None) -> Dict[str, Any]:
        data = dict(payload or {})

        # Short-circuit validation for midwife role: only findings required
        if role and str(role).lower() == 'midwife':
            # If a monitoring id is provided, ensure the existing row doesn't already
            # have findings recorded. Prevent midwife updates if findings exist.
            monitor_id = (
                data.get('child_monitoring_id')
                or data.get('monitoring_id')
                or data.get('child_monitor_id')
                or data.get('id')
            )
            if monitor_id and self._monitoring_query:
                try:
                    existing = self._monitoring_query.fetch_by_monitoring_id(int(monitor_id))
                except Exception as e:
                    logger.warning('Failed to fetch existing monitoring row: %s', e)
                    existing = None
                if existing and existing.get('findings') not in (None, ''):
                    msg = MessageCatalog.translate('findings_already_present')
                    logger.warning('ChildVisit validation failed (midwife): %s', msg)
                    raise ChildVisitDomainException(msg, code='findings_already_present')

            findings = data.get('findings')
            notes = data.get('notes')
            if findings in (None, ''):
                msg = MessageCatalog.translate('findings_required')
                logger.warning('ChildVisit validation failed (midwife): %s', msg)
                raise ChildVisitDomainException(msg, code='findings_required')
            try:
                findings_clean = ValidationUtils.sanitize_no_emoji(str(findings))
                notes_clean = ValidationUtils.sanitize_no_emoji(str(notes)) if notes is not None else None
            except ValueError:
                msg = MessageCatalog.translate('emoji_not_allowed')
                raise ChildVisitDomainException(msg, code='emoji_not_allowed')
            return {'findings': findings_clean, 'notes': notes_clean}
        # Age
        age_raw = data.get("age")
        if age_raw in (None, ""):
            msg = MessageCatalog.translate("age_required")
            logger.warning("ChildVisit validation failed: %s", msg)
            raise ChildVisitDomainException(msg, code="age_required")
        try:
            age_val = ValidationUtils.parse_decimal(age_raw)
        except ValueError:
            msg = MessageCatalog.translate("age_invalid")
            raise ChildVisitDomainException(msg, code="age_invalid")

        if age_val >= Decimal("5"):
            msg = MessageCatalog.translate("age_limit")
            raise ChildVisitDomainException(msg, code="age_limit")

        # Disallow negative ages
        if age_val < Decimal("0"):
            msg = MessageCatalog.translate("age_negative")
            raise ChildVisitDomainException(msg, code="age_negative")

        # If age >= 1, require integer-like value
        if age_val >= Decimal("1") and age_val != age_val.to_integral_value():
            msg = MessageCatalog.translate("age_integer_required")
            raise ChildVisitDomainException(msg, code="age_integer_required")

        data["age"] = age_val

        # Weight
        weight_raw = data.get("weight")
        if weight_raw in (None, ""):
            msg = MessageCatalog.translate("weight_required")
            raise ChildVisitDomainException(msg, code="weight_required")
        try:
            weight = ValidationUtils.parse_decimal(weight_raw)
        except ValueError:
            msg = MessageCatalog.translate("weight_invalid")
            raise ChildVisitDomainException(msg, code="weight_invalid")
        if weight < self.MIN_WEIGHT or weight > self.MAX_WEIGHT:
            msg = MessageCatalog.translate("weight_range", min=self.MIN_WEIGHT, max=self.MAX_WEIGHT)
            raise ChildVisitDomainException(msg, code="weight_range")
        data["weight"] = weight

        # Temperature
        temp_raw = data.get("temp")
        if temp_raw in (None, ""):
            msg = MessageCatalog.translate("temp_required")
            raise ChildVisitDomainException(msg, code="temp_required")
        try:
            temp = ValidationUtils.parse_decimal(temp_raw)
        except ValueError:
            msg = MessageCatalog.translate("temp_invalid")
            raise ChildVisitDomainException(msg, code="temp_invalid")
        if temp < self.MIN_TEMP or temp > self.MAX_TEMP:
            msg = MessageCatalog.translate("temp_range", min=self.MIN_TEMP, max=self.MAX_TEMP)
            raise ChildVisitDomainException(msg, code="temp_range")
        data["temp"] = temp

        # Height (cm)
        height_raw = data.get("height")
        if height_raw in (None, ""):
            msg = MessageCatalog.translate("height_required")
            raise ChildVisitDomainException(msg, code="height_required")
        try:
            height = ValidationUtils.parse_decimal(height_raw)
        except ValueError:
            msg = MessageCatalog.translate("height_invalid")
            raise ChildVisitDomainException(msg, code="height_invalid")
        if height < self.MIN_HEIGHT or height > self.MAX_HEIGHT:
            msg = MessageCatalog.translate("height_range", min=self.MIN_HEIGHT, max=self.MAX_HEIGHT)
            raise ChildVisitDomainException(msg, code="height_range")
        data["height"] = height

        # Findings (optional for non-midwife flows). If present, sanitize.
        findings = data.get('findings')
        if findings not in (None, ''):
            try:
                findings_clean = ValidationUtils.sanitize_no_emoji(str(findings))
            except ValueError:
                msg = MessageCatalog.translate('emoji_not_allowed')
                raise ChildVisitDomainException(msg, code='emoji_not_allowed')
            data['findings'] = findings_clean

        # Notes optional; if missing, set to 'N/A'
        notes = data.get("notes")
        if notes in (None, ""):
            data["notes"] = MessageCatalog.translate("notes_na")
        else:
            try:
                notes_clean = ValidationUtils.sanitize_no_emoji(str(notes))
            except ValueError:
                msg = MessageCatalog.translate("emoji_not_allowed")
                raise ChildVisitDomainException(msg, code="emoji_not_allowed")
            data["notes"] = notes_clean

        logger.info("ChildVisit payload validated for chr payload keys: %s", list(data.keys()))
        return data
