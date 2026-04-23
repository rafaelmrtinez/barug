from __future__ import annotations
from typing import Dict, Any, Optional, Set
from datetime import date

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.form_utils import FormUtils


class TetanusToxoidValidationException(Exception):
    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class TetanusToxoidService:
    """Service that validates and persists maternal tetanus toxoid entries.

    This replicates the rules in `TetanusToxoidForm.clean()` and returns
    `tt_id` and `last_entry` suitable for the repository insertion.
    """

    LABEL_TO_FIELD = {
        "TT1": "tt1_date",
        "TT2": "tt2_date",
        "TT3": "tt3_date",
        "TT4": "tt4_date",
        "TT5": "tt5_date",
    }

    FIELD_TO_NUMBER = {
        'tt1_date': 1,
        'tt2_date': 2,
        'tt3_date': 3,
        'tt4_date': 4,
        'tt5_date': 5,
        'fim_date': 6,
    }

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

        # Fetch existing TT records if repository available
        mhr_id = payload.get('mhr_id')
        existing_rows = []
        existing_by_number: Dict[int, Dict[str, Any]] = {}
        if self.repository and mhr_id:
            try:
                existing_rows = self.repository.fetch_maternal_tt_by_mhr_id(mhr_id) or []
            except Exception:
                existing_rows = []

        # Build existing_numbers and existing_dates
        existing_numbers: Set[int] = set()
        existing_dates: Set[date] = set()
        TYPE_TO_INDEX = {"TT1": 1, "TT2": 2, "TT3": 3, "TT4": 4, "TT5": 5, "FIM": 6}
        for row in existing_rows:
            tt_name = (row.get('tt_type_name') or '').upper()
            nn = TYPE_TO_INDEX.get(tt_name)
            if nn:
                existing_numbers.add(nn)
                dt = row.get('date_given')
                if isinstance(dt, date):
                    existing_dates.add(dt)
                existing_by_number[nn] = {'tt_id': row.get('tt_id'), 'date_given': row.get('date_given')}

        # If all doses recorded, disallow further entries
        if existing_numbers >= set(range(1, 7)):
            raise TetanusToxoidValidationException(message='All Tetanus Toxoid doses have already been recorded.', errors={})

        # Collect submitted dates
        submitted_numbers: Set[int] = set()
        submitted_dates: Dict[int, date] = {}
        for field, num in self.FIELD_TO_NUMBER.items():
            raw = payload.get(field)
            dt = self._parse_date(raw)
            if dt is not None:
                submitted_numbers.add(num)
                submitted_dates[num] = dt
                cleaned[field] = dt

        # require at least one date
        if not submitted_numbers:
            raise TetanusToxoidValidationException(message='At least one Tetanus Toxoid date must be provided.', errors={})

        # Require TT1 if others are submitted and TT1 not present
        if any(n != 1 for n in submitted_numbers) and 1 not in existing_numbers and 1 not in submitted_numbers:
            raise TetanusToxoidValidationException(message='TT1 date is required if any other TT date is provided.', errors={})

        # Duplicate/overwrite checks and date collisions
        for num, dt in submitted_dates.items():
            if num in existing_numbers:
                existing_info = existing_by_number.get(num, {})
                existing_date_for_same_dose = existing_info.get('date_given')
                if dt == existing_date_for_same_dose:
                    # unchanged for same dose; allow
                    continue
                else:
                    # attempting to change an existing dose
                    field_name = next(k for k, v in self.FIELD_TO_NUMBER.items() if v == num)
                    errors.setdefault(field_name, []).append(f"TT{num} has already been recorded on {existing_date_for_same_dose}. To change it, edit the existing record.")
                    continue
            # check date collision with other existing dates
            if dt in existing_dates:
                field_name = next(k for k, v in self.FIELD_TO_NUMBER.items() if v == num)
                errors.setdefault(field_name, []).append(f"A tetanus dose has already been recorded on {dt}. Please choose a different date.")

        # Ensure submitted dates are unique among themselves
        if len(submitted_dates.values()) != len(set(submitted_dates.values())):
            raise TetanusToxoidValidationException(message='Please ensure submitted TT dates are unique — duplicate dates were provided.', errors={})

        # No skipped doses: for each submitted dose, all prior doses must be present (existing or submitted)
        combined = existing_numbers.union(submitted_numbers)
        for num in sorted(submitted_numbers):
            for prior in range(1, num):
                if prior not in combined:
                    field_name = next(k for k, v in self.FIELD_TO_NUMBER.items() if v == num)
                    errors.setdefault(field_name, []).append(f"Cannot record TT{num} before TT{prior} is recorded. Please record earlier doses first.")

        # Chronological order checks
        combined_dates = {}
        for n in range(1, 7):
            if n in submitted_dates:
                combined_dates[n] = submitted_dates[n]
            elif n in existing_by_number:
                combined_dates[n] = existing_by_number[n].get('date_given')
            else:
                combined_dates[n] = None

        for n in range(2, 7):
            prev = combined_dates.get(n-1)
            curr = combined_dates.get(n)
            if prev is not None and curr is not None:
                if curr < prev:
                    field_name = next(k for k, v in self.FIELD_TO_NUMBER.items() if v == n)
                    errors.setdefault(field_name, []).append(f"TT{n} date ({curr}) cannot be earlier than TT{n-1} date ({prev}). Please correct the dates.")

        if errors:
            raise TetanusToxoidValidationException(message='Please check the entered values.', errors=errors)

        # Determine last_entry and tt_id to insert (last non-None among fim_date then tt5..tt1)
        last_field = None
        last_value = None
        tt_id = None
        if cleaned.get('fim_date') is not None:
            last_field = 'fim_date'
            last_value = cleaned.get('fim_date')
            tt_id = 6
        else:
            for i in range(5, 0, -1):
                fname = f'tt{i}_date'
                if cleaned.get(fname) is not None:
                    last_field = fname
                    last_value = cleaned.get(fname)
                    tt_id = i
                    break

        if tt_id is None:
            # Should not happen due to earlier checks
            raise TetanusToxoidValidationException(message='No valid TT entry found.', errors={})

        cleaned['last_entry'] = last_value
        cleaned['tt_id'] = tt_id
        cleaned.setdefault('mhr_id', mhr_id)
        return cleaned

    def save_tetanus_tt(self, payload: Dict[str, Any], staff_id: int):
        cleaned = self.validate(payload)

        if not self.repository:
            raise ServiceExecutionException('Repository not available for save operation.')

        try:
            return self.repository.insert_maternal_tt_record(
                mhr_id=cleaned.get('mhr_id'),
                staff_id=staff_id,
                tt_type_id=cleaned.get('tt_id'),
                date_given=cleaned.get('last_entry'),
            )
        except MaternalHealthRecordException:
            raise
        except Exception:
            raise ServiceExecutionException('Failed to persist tetanus record.')
