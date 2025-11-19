from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import date

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.form_utils import FormUtils


class PreviousPregnancyValidationException(Exception):
    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class PreviousPregnancyService:
    """Service to validate and persist previous pregnancy entries.

    Mirrors the `PreviousPregnancyForm` validation rules and maps choice
    values to IDs expected by the repository.
    """

    def __init__(self, repository: Optional[MaternalHealthRecordRepository] = None):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        errors: Dict[str, Any] = {}
        cleaned: Dict[str, Any] = {}

        # delivery_date
        delivery_date = payload.get("delivery_date")
        if delivery_date is None:
            errors.setdefault("delivery_date", []).append("Delivery date is required.")
        else:
            # payload may contain a string (from JSON) or a date object; try to handle conservatively
            try:
                if isinstance(delivery_date, str):
                    # assume ISO date string
                    delivery_date_parsed = date.fromisoformat(delivery_date)
                elif isinstance(delivery_date, date):
                    delivery_date_parsed = delivery_date
                else:
                    raise ValueError("Invalid date format")

                if delivery_date_parsed > date.today():
                    errors.setdefault("delivery_date", []).append("Delivery date cannot be in the future.")
                else:
                    cleaned["delivery_date"] = delivery_date_parsed
            except Exception:
                errors.setdefault("delivery_date", []).append("Invalid delivery date format.")

        # baby_weight_kg
        baby_weight = payload.get("baby_weight_kg")
        if baby_weight is None:
            errors.setdefault("baby_weight_kg", []).append("Baby's weight is required.")
        else:
            try:
                # accept string or numeric
                bw = float(baby_weight)
                if bw <= 0:
                    errors.setdefault("baby_weight_kg", []).append("Baby's weight must be greater than zero.")
                elif bw > 10:
                    errors.setdefault("baby_weight_kg", []).append("Please confirm the baby's weight — values over 10 kg are unusual.")
                else:
                    cleaned["baby_weight_kg"] = bw
            except Exception:
                errors.setdefault("baby_weight_kg", []).append("Invalid baby weight value.")

        # ballard_score (0-50)
        ballard = payload.get("ballard_score")
        if ballard is None:
            errors.setdefault("ballard_score", []).append("Ballard score is required.")
        else:
            try:
                b = int(ballard)
                if b < 0 or b > 50:
                    errors.setdefault("ballard_score", []).append("Ballard score must be between 0 and 50.")
                else:
                    cleaned["ballard_score"] = b
            except Exception:
                errors.setdefault("ballard_score", []).append("Please enter a whole number for the Ballard score.")

        # apgar_score (0-10)
        apgar = payload.get("apgar_score")
        if apgar is None:
            errors.setdefault("apgar_score", []).append("Apgar score is required.")
        else:
            try:
                a = int(apgar)
                if a < 0 or a > 10:
                    errors.setdefault("apgar_score", []).append("Apgar score must be between 0 and 10.")
                else:
                    cleaned["apgar_score"] = a
            except Exception:
                errors.setdefault("apgar_score", []).append("Please enter a whole number for the Apgar score.")

        # choices: outcome, delivery_type, gender — sanitize and map to ids
        for field_name, label in (("outcome", "Outcome"), ("delivery_type", "Type of delivery"), ("gender", "Gender")):
            val = payload.get(field_name)
            if val is None or str(val).strip() == "":
                errors.setdefault(field_name, []).append(f"Please select {label.lower()}.")
            else:
                normalized = FormUtils.remove_non_printable(str(val).strip())
                if FormUtils.contains_emoji(normalized):
                    errors.setdefault(field_name, []).append(f"{label}: please remove emojis — use plain text only.")
                else:
                    cleaned[field_name] = normalized

        # map delivery_type and gender to IDs (keep existing mapping used by form)
        delivery_type = str(cleaned.get("delivery_type") or "").lower()
        if delivery_type:
            if delivery_type == 'nsvd':
                cleaned['delivery_type_id'] = 1
            elif delivery_type == 'cs':
                cleaned['delivery_type_id'] = 2

        gender = str(cleaned.get("gender") or "").lower()
        if gender:
            if gender == 'female':
                cleaned['gender_id'] = 2
            elif gender == 'male':
                cleaned['gender_id'] = 1

        if errors:
            raise PreviousPregnancyValidationException(message="Please check the entered values.", errors=errors)

        cleaned.setdefault("mhr_id", payload.get("mhr_id"))
        return cleaned

    def save_previous_pregnancy(self, payload: Dict[str, Any], staff_id: int):
        cleaned = self.validate(payload)

        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        try:
            return self.repository.insert_previous_pregnancy_info(
                mhr_id=cleaned.get('mhr_id'),
                staff_id=staff_id,
                date_of_delivery=cleaned.get('delivery_date'),
                outcome=cleaned.get('outcome'),
                baby_weight_kg=cleaned.get('baby_weight_kg'),
                ballard_score=cleaned.get('ballard_score'),
                apgar_score=cleaned.get('apgar_score'),
                delivery_type_id=cleaned.get('delivery_type_id'),
                sex=cleaned.get('gender_id'),
            )
        except MaternalHealthRecordException:
            # Let domain exception propagate so API can convert using error codes
            raise
        except Exception:
            raise ServiceExecutionException("Failed to persist previous pregnancy info.")
