from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import date

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


class PresentPregnancyValidationException(Exception):
    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class PresentPregnancyService:
    """Service that validates and persists present pregnancy data.

    Mirrors the logic from `PresentPregnancyForm.clean()` but as a
    testable service layer. Returns cleaned values for persistence and
    raises `PresentPregnancyValidationException` for user-facing errors.
    """

    def __init__(self, repository: Optional[MaternalHealthRecordRepository] = None):
        self.repository = repository

    def _parse_date(self, raw) -> Optional[date]:
        if raw is None:
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except Exception:
                return None
        return None

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        errors: Dict[str, Any] = {}
        cleaned: Dict[str, Any] = {}

        mhr_id = payload.get('mhr_id')

        # Check existing record: if present, prevent creating a new one
        existing = None
        if self.repository and mhr_id:
            try:
                existing = self.repository.fetch_latest_present_pregnancy_by_mhr_id(mhr_id)
            except Exception:
                existing = None

        if existing and isinstance(existing, dict):
            # If client attempted to submit (POST) values while a record exists,
            # block creation.
            submitted_values_present = any(k in payload for k in ('gravida', 'para', 'fullterm', 'preterm', 'lmp', 'edc'))
            if submitted_values_present:
                errors.setdefault('__all__', []).append(
                    "A present pregnancy record already exists for this patient. To change values, please edit the existing record or contact your administrator."
                )
                raise PresentPregnancyValidationException(message="Duplicate entry", errors=errors)

        # Gravida / Para (optional but must be non-negative integers if provided)
        gravida = payload.get('gravida')
        if gravida is not None and gravida != '':
            try:
                g = int(gravida)
                if g < 0:
                    errors.setdefault('gravida', []).append('Gravida cannot be negative.')
                else:
                    cleaned['gravida'] = g
            except Exception:
                errors.setdefault('gravida', []).append('Please enter a whole number for gravida.')

        para = payload.get('para')
        if para is not None and para != '':
            try:
                p = int(para)
                if p < 0:
                    errors.setdefault('para', []).append('Para cannot be negative.')
                else:
                    cleaned['para'] = p
            except Exception:
                errors.setdefault('para', []).append('Please enter a whole number for para.')

        # fullterm / preterm: required boolean-like (expect '1'/'0', True/False, or JSON booleans)
        def parse_bool(v):
            if v is None or v == '':
                return None
            if isinstance(v, bool):
                return v
            s = str(v).strip()
            if s == '1' or s.lower() in ('true', 't', 'yes'):
                return True
            if s == '0' or s.lower() in ('false', 'f', 'no'):
                return False
            return None

        fullterm_raw = payload.get('fullterm')
        fullterm = parse_bool(fullterm_raw)
        if fullterm is None:
            errors.setdefault('fullterm', []).append('Please select Fullterm (Yes or No).')
        else:
            cleaned['fullterm'] = fullterm

        preterm_raw = payload.get('preterm')
        preterm = parse_bool(preterm_raw)
        if preterm is None:
            errors.setdefault('preterm', []).append('Please select Preterm (Yes or No).')
        else:
            cleaned['preterm'] = preterm

        # LMP and EDC (required and must be chronological)
        lmp_raw = payload.get('lmp')
        edc_raw = payload.get('edc')
        lmp = self._parse_date(lmp_raw)
        edc = self._parse_date(edc_raw)

        if lmp is None:
            errors.setdefault('lmp', []).append('LMP is required and must be a valid date (YYYY-MM-DD).')
        else:
            cleaned['lmp'] = lmp

        if edc is None:
            errors.setdefault('edc', []).append('EDC is required and must be a valid date (YYYY-MM-DD).')
        else:
            cleaned['edc'] = edc

        if lmp is not None and edc is not None:
            if lmp > edc:
                errors.setdefault('edc', []).append('EDC cannot be earlier than LMP. Please correct the dates.')

        if errors:
            raise PresentPregnancyValidationException(message='Please check the entered values.', errors=errors)

        cleaned.setdefault('mhr_id', mhr_id)
        return cleaned

    def save_present_pregnancy(self, payload: Dict[str, Any], staff_id: int):
        cleaned = self.validate(payload)

        if not self.repository:
            raise ServiceExecutionException('Repository not available for save operation.')

        try:
            return self.repository.insert_present_pregnancy_status(
                mhr_id=cleaned.get('mhr_id'),
                staff_id=staff_id,
                gravida=cleaned.get('gravida'),
                para=cleaned.get('para'),
                is_fullterm=cleaned.get('fullterm'),
                is_preterm=cleaned.get('preterm'),
                lmp=cleaned.get('lmp'),
                edc=cleaned.get('edc'),
            )
        except MaternalHealthRecordException:
            # propagate domain errors to API for mapping/filtering
            raise
        except Exception:
            raise ServiceExecutionException('Failed to persist present pregnancy status.')
