import logging
from datetime import date
from typing import Any, Dict, List, Optional

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility

logger = logging.getLogger(__name__)


class BFFeedingService:
    """Service to validate and persist exclusive breastfeeding check dates.

    Moves the validation logic previously in `ChildBreastFeedingForm.clean()` into
    an application service. It returns the repository result on success and
    raises `ChildHealthRecordException` with a helpful message on validation errors.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository):
        self._repo = ch_repo

    def _normalize_slots(self, data: Dict[str, Any], slots: List[str]) -> List[Optional[date]]:
        out = []
        for fname in slots:
            val = data.get(fname)
            if isinstance(val, str):
                parsed = DateAndTimeUtility.parse_date(val)
                if parsed:
                    out.append(parsed)
                    continue
            if hasattr(val, 'date') and callable(getattr(val, 'date')):
                # datetime-like
                try:
                    out.append(val.date())
                    continue
                except Exception:
                    pass
            out.append(None)
        return out

    def process_and_insert(self, chr_id: int, staff_id: int, payload: Dict[str, Any]) -> Any:
        """Validate payload and insert a new BF check when appropriate.

        Expects either `exclusive_bf_check_last` or slot fields `exclusive_bf_check_1..5`.
        On validation error raises `ChildHealthRecordException`.
        """
        data = dict(payload or {})
        data.pop('form_type', None)

        slot_fields = [f"exclusive_bf_check_{i}" for i in range(1, 6)]
        incoming = self._normalize_slots(data, slot_fields)

        # If explicit last provided prefer it (normalize it)
        explicit_last = data.get('exclusive_bf_check_last')
        if explicit_last:
            if isinstance(explicit_last, str):
                parsed = DateAndTimeUtility.parse_date(explicit_last)
                explicit_last = parsed
            elif hasattr(explicit_last, 'date') and callable(getattr(explicit_last, 'date')):
                try:
                    explicit_last = explicit_last.date()
                except Exception:
                    explicit_last = None

        # If no data at all, error
        if all(v is None for v in incoming) and not explicit_last:
            raise ChildHealthRecordException('Please provide at least one exclusive breastfeeding check date.')

        # If explicit last exists, treat as the last non-null
        if explicit_last and not any(incoming):
            last_non_null = explicit_last
        else:
            # derive non-null list from incoming slots
            incoming_non_null = [d for d in incoming if d is not None]
            # rule: no holes
            for i in range(len(incoming)):
                if incoming[i] is None:
                    # if there's any later non-null, report that later visit index
                    for j in range(i + 1, len(incoming)):
                        if incoming[j] is not None:
                            # report the visit number of the first later non-null slot (1-based)
                            raise ChildHealthRecordException(
                                f'Please fill earlier visit(s) before adding a date for Visit {j+1}.'
                            )
            last_non_null = incoming_non_null[-1] if incoming_non_null else None

        # date sanity: no future dates
        try:
            ph_today_str = DateAndTimeUtility.get_current_date()
            today = DateAndTimeUtility.parse_date(ph_today_str) or date.today()
        except Exception:
            today = date.today()

        if last_non_null and last_non_null > today:
            raise ChildHealthRecordException('One or more dates are in the future. Please use today or past dates only.')

        # existing entries from repository (ordered earliest->latest expected)
        existing_rows = self._repo.fetch_child_details_bf_display_by_chr_id(chr_id) or []
        existing_dates: List[date] = []
        if isinstance(existing_rows, list):
            # extract check_date similar to form init logic
            rows = sorted(existing_rows, key=lambda r: (r.get('visit_id') or 0))
            for row in rows[:5]:
                cd = row.get('check_date')
                if isinstance(cd, str):
                    parsed = DateAndTimeUtility.parse_date(cd)
                    if parsed:
                        existing_dates.append(parsed)
                elif hasattr(cd, 'date') and callable(getattr(cd, 'date')):
                    try:
                        existing_dates.append(cd.date())
                    except Exception:
                        continue
                elif cd is not None:
                    existing_dates.append(cd)

        # If existing, enforce rules
        if existing_dates:
            # if fewer new non-null than existing -> cannot remove
            new_non_null = [d for d in incoming if d is not None]
            if len(new_non_null) < len(existing_dates):
                raise ChildHealthRecordException('Cannot remove previously recorded check dates. To modify existing entries, edit the original record.')

            # ensure prefix equal
            prefix = new_non_null[: len(existing_dates)]
            if prefix != existing_dates:
                raise ChildHealthRecordException('Existing check dates may not be modified. To change them, edit the original record.')

            if len(new_non_null) == len(existing_dates):
                raise ChildHealthRecordException('No changes detected — the submitted dates match existing records.')

            if len(new_non_null) > len(existing_dates):
                new_entries = new_non_null[len(existing_dates):]
                last_existing = existing_dates[-1]
                prev = last_existing
                for d in new_entries:
                    if d <= prev:
                        raise ChildHealthRecordException('Newly added check dates must be after the previously recorded date.')
                    prev = d
                # final date to insert
                check_date = new_entries[-1]
        else:
            # no existing entries — ensure strictly increasing
            new_non_null = [d for d in incoming if d is not None]
            for i in range(1, len(new_non_null)):
                if new_non_null[i] <= new_non_null[i-1]:
                    raise ChildHealthRecordException('Breastfeeding check dates must be in chronological order and each date must be later than the previous one.')
            check_date = new_non_null[-1] if new_non_null else (explicit_last or None)

        if not check_date:
            raise ChildHealthRecordException('No valid check date to save.')

        # Persist
        is_success = self._repo.insert_bf_check(
            p_child_record_id=chr_id,
            p_assessed_by_id=staff_id,
            p_check_date=check_date,
        )
        if not is_success:
            raise ChildHealthRecordException('Failed to save BF data')
        return is_success
