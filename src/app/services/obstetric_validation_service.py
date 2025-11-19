"""Obstetric validation service.

This module contains cross-field and business-rule validation logic and
an orchestration service that validates and persists obstetric history.

Design goals:
- Move cross-field/business rules to a testable service layer.
- Surface only validation errors to clients; internal failures are
  wrapped and should be returned as generic server errors by the API.
- Provide clear, chronological, actionable error messages.
"""
from __future__ import annotations
from typing import Optional, Dict, Any

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


class ObstetricValidationException(Exception):
    """Raised when obstetric validation fails in the service layer.

    The `errors` attribute is a mapping of field -> list-of-errors to match
    Django form error structures (e.g. `{ 'field': ['msg'] }`).
    """

    def __init__(self, message: str = "Validation failed.", errors: Dict[str, Any] | None = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    """Raised when the service fails to perform persistence or orchestration.

    These are considered internal errors and should not be sent to the
    client; the API layer should convert this to a generic 500 response.
    """


def _to_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


class ObstetricValidationService:
    """Service responsible for validating and orchestrating obstetric data.

    Responsibilities:
    - Validate cross-field and business rules via `validate()`.
    - Orchestrate persistence via `save_obstetric_history()` using the
      provided repository.

    The service raises `ObstetricValidationException` for user-facing
    validation errors and `ServiceExecutionException` for internal failures.
    """

    MAX_PER_FIELD = 50
    MAX_TOTAL_OUTCOMES = 200

    def __init__(self, repository: Optional[MaternalHealthRecordRepository] = None):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        print( "payload in service:", payload)
        """Run ordered validations and return parsed values on success.

        Steps (chronological):
        1. Requiredness & integer parsing for key numeric fields.
        2. Optional boolean parsing.
        3. Logical cross-field consistency checks.
        4. Plausibility and heuristic caps.
        5. Duplicate detection (if repository and mhr_id provided).

        Returns:
            dict: parsed and typed values ready for persistence.

        Raises:
            ObstetricValidationException: with field-level errors when validation fails.
        """
        errors: Dict[str, Any] = {}

        # 1) Requiredness and integer parsing
        int_fields = [
            ("children_born_alive", "No. of children born alive"),
            ("living_children", "No. of living children"),
            ("abortions", "No. of abortions"),
            ("stillbirths", "No. of still births / fetal death"),
            ("history_large_babies", "History of large babies"),
        ]

        parsed: Dict[str, Any] = {}
        for key, label in int_fields:
            if key not in payload:
                errors.setdefault(key, []).append(f"{label} is required.")
                continue
            raw = payload.get(key)
            val = _to_int(raw)
            if val is None:
                errors.setdefault(key, []).append(f"Please enter a whole number for {label}.")
                continue
            if val < 0:
                errors.setdefault(key, []).append(f"{label} cannot be negative.")
                continue
            parsed[key] = val

        # 2) Optional boolean parsing for has_diabetes
        # Accept both `has_diabetes` and legacy/frontend `diabetes_history` keys
        if "has_diabetes" in payload or "diabetes_history" in payload:
            raw = payload.get("has_diabetes", payload.get("diabetes_history"))
            if isinstance(raw, bool):
                parsed["has_diabetes"] = raw
            elif isinstance(raw, str):
                low = raw.strip().lower()
                if low in ("t", "true", "1", "yes"):
                    parsed["has_diabetes"] = True
                elif low in ("f", "false", "0", "no"):
                    parsed["has_diabetes"] = False
                else:
                    errors.setdefault("has_diabetes", []).append("Invalid value for diabetes (use true/false).")
            else:
                errors.setdefault("has_diabetes", []).append("Invalid value for diabetes.")
        else:
            parsed["has_diabetes"] = None

        # Stop early if parse errors
        if errors:
            raise ObstetricValidationException(message="Please check the entered values.", errors=errors)

        # 3) Logical / cross-field checks
        cba = parsed.get("children_born_alive")
        lc = parsed.get("living_children")
        ab = parsed.get("abortions")
        sb = parsed.get("stillbirths")
        lb = parsed.get("history_large_babies")

        if lc is not None and cba is not None and lc > cba:
            errors.setdefault("living_children", []).append(
                "Living children cannot exceed number of children born alive."
            )

        if lb is not None and cba is not None and lb > cba:
            errors.setdefault("history_large_babies", []).append(
                "Number of large babies cannot exceed number of children born alive."
            )

        # 4) Plausibility checks
        total_outcomes = (cba or 0) + (sb or 0) + (ab or 0)
        if total_outcomes > self.MAX_TOTAL_OUTCOMES:
            errors.setdefault("__all__", []).append(
                "The combined total of births, stillbirths and abortions looks unusually large — please verify the entries."
            )

        if cba is not None and cba > self.MAX_PER_FIELD:
            errors.setdefault("children_born_alive", []).append(
                "Please verify the number of children born alive."
            )
        if ab is not None and ab > self.MAX_PER_FIELD:
            errors.setdefault("abortions", []).append(
                "Please verify the number of abortions."
            )
        if sb is not None and sb > self.MAX_PER_FIELD:
            errors.setdefault("stillbirths", []).append(
                "Please verify the number of stillbirths / fetal deaths."
            )

        # 5) Duplicate detection
        mhr_id = payload.get("mhr_id")
        if self.repository and mhr_id:
            try:
                existing = self.repository.fetch_obstetric_history_by_mhr_id(mhr_id)
                if existing:
                    errors.setdefault("__all__", []).append(
                        "Obstetric history already exists for this record. To update, please use the edit flow or contact an administrator."
                    )
            except Exception:
                # repository errors should not become user validation errors
                pass

        if errors:
            raise ObstetricValidationException(message="Please check the entered values.", errors=errors)

        parsed.setdefault("mhr_id", mhr_id)
        return parsed

    def save_obstetric_history(self, payload: Dict[str, Any], staff_id: int):
        """Validate then persist obstetric history using the repository.

        Returns the repository result on success. Raises:
        - ObstetricValidationException for validation errors (user-facing)
        - ServiceExecutionException for internal/persistence failures
        """
        parsed = self.validate(payload)
        print( "parsed in service:", parsed)

        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        try:
            return self.repository.insert_obstetric_history(
                mhr_id=parsed.get("mhr_id"),
                added_by_id=staff_id,
                num_children_born_alive=parsed.get("children_born_alive"),
                num_children_living=parsed.get("living_children"),
                num_of_abortions=parsed.get("abortions"),
                num_stillbirth=parsed.get("stillbirths"),
                num_large_babies=parsed.get("history_large_babies"),
                has_diabetes=parsed.get("has_diabetes"),
            )
        except MaternalHealthRecordException:
            # Let domain exception propagate so API can surface friendly message
            raise
        except Exception as exc:
            raise ServiceExecutionException("Failed to persist obstetric history.") from exc
