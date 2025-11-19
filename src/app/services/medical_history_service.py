from __future__ import annotations
from typing import Dict, Any, Optional

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.form_utils import FormUtils


class MedicalHistoryValidationException(Exception):
    """Raised when medical history validation fails.

    The `errors` attribute is a mapping similar to Django form errors.
    """

    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class MedicalHistoryService:
    """Service that validates and persists medical history entries.

    This mirrors the behaviour previously implemented in `MedicalHistoryForm`:
    - sanitize text fields via `FormUtils.sanitize_text`
    - prevent duplicate insertion when a record already exists for the MHR
    - persist using the `MaternalHealthRecordRepository`
    """

    def __init__(self, repository: Optional[MaternalHealthRecordRepository] = None):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        errors: Dict[str, Any] = {}
        text_fields = [
            ("previous_illness", "Previous illness"),
            ("previous_hospitalization", "Previous hospitalization"),
            ("previous_preg_complications", "Previous pregnancy complications"),
        ]

        cleaned: Dict[str, Any] = {}

        # duplicate check: if existing record exists for mhr_id, do not allow re-entry
        mhr_id = payload.get("mhr_id")
        existing = None
        if self.repository and mhr_id:
            try:
                existing = self.repository.fetch_medical_history_by_mhr_id(mhr_id)
            except Exception:
                # do not convert infra errors into user-facing validation
                existing = None

        if existing:
            # if any submitted non-empty values are present, reject as duplicate
            submitted_values = [payload.get(name) for name, _ in text_fields]
            if any(v is not None and str(v).strip() != "" for v in submitted_values):
                errors.setdefault("__all__", []).append(
                    "A medical history for this record already exists. To update, use the edit flow or contact an administrator."
                )
                raise MedicalHistoryValidationException(message="Please check the entered values.", errors=errors)

        # sanitize each text field
        for field_name, label in text_fields:
            raw = payload.get(field_name)
            if raw is None:
                errors.setdefault(field_name, []).append(f"{label} is required. Please enter text or 'N/A'.")
                continue
            normalized, error = FormUtils.sanitize_text(raw, label)
            if error:
                errors.setdefault(field_name, []).append(error)
                continue
            cleaned[field_name] = normalized

        if errors:
            raise MedicalHistoryValidationException(message="Please check the entered values.", errors=errors)

        cleaned.setdefault("mhr_id", mhr_id)
        return cleaned

    def save_medical_history(self, payload: Dict[str, Any], staff_id: int):
        """Validate and persist medical history. Returns repository result on success.

        Raises:
            MedicalHistoryValidationException: for user-facing validation errors
            ServiceExecutionException: for internal/persistence errors
        """
        cleaned = self.validate(payload)

        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        try:
            return self.repository.insert_medical_history(
                mhr_id=cleaned.get("mhr_id"),
                staff_id=staff_id,
                previous_illness=cleaned.get("previous_illness"),
                previous_hostpitalzation=cleaned.get("previous_hospitalization"),
                previous_complication=cleaned.get("previous_preg_complications"),
            )
        except MaternalHealthRecordException:
            # propagate domain exception for API layer to surface friendly message
            raise
        except Exception as exc:
            raise ServiceExecutionException("Failed to persist medical history.") from exc
