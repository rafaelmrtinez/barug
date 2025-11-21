from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List, Optional

from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.domain.exceptions.bf_feeding_domain_exception import BfFeedingDomainException


class BFFeedingDomainService:
    """Domain service for BF feeding rules.

    Responsible for validating and computing the single date that should
    be inserted as a breastfeeding check. Raises domain exceptions for
    invalid payloads or rule violations.
    """

    def __init__(self, ch_repo: IChildHealthRecordRepository):
        self.ch_repo = ch_repo

    def _parse_single(self, val: Any) -> Optional[date]:
        if val is None or val == "":
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, str):
            parsed = DateAndTimeUtility.parse_date(val)
            if parsed is None:
                # invalid date format provided
                raise BfFeedingDomainException(f"Invalid date format: {val}")
            return parsed
        # try datetime-like
        if hasattr(val, 'date') and callable(getattr(val, 'date')):
            try:
                return val.date()
            except Exception:
                return None
        return None

    def determine_check_date(self, chr_id: int, payload: Dict[str, Any]) -> date:
        data = dict(payload or {})
        data.pop('form_type', None)

        slot_fields = [f"exclusive_bf_check_{i}" for i in range(1, 6)]
        incoming: List[Optional[date]] = [self._parse_single(data.get(f)) for f in slot_fields]

        explicit_last = self._parse_single(data.get('exclusive_bf_check_last'))

        # Ensure at least one date provided
        if all(v is None for v in incoming) and explicit_last is None:
            raise BfFeedingDomainException('Please provide at least one exclusive breastfeeding check date.')

        # Determine last_non_null similarly to previous service behavior
        if explicit_last and not any(incoming):
            last_non_null = explicit_last
        else:
            incoming_non_null = [d for d in incoming if d is not None]
            # rule: no holes
            for i in range(len(incoming)):
                if incoming[i] is None:
                    for j in range(i + 1, len(incoming)):
                        if incoming[j] is not None:
                            raise BfFeedingDomainException(
                                f'Please fill earlier visit(s) before adding a date for Visit {j+1}.'
                            )
            last_non_null = incoming_non_null[-1] if incoming_non_null else None

        # date sanity: no future dates based on Manila timezone
        try:
            ph_today_str = DateAndTimeUtility.get_current_date()
            today = DateAndTimeUtility.parse_date(ph_today_str) or date.today()
        except Exception:
            today = date.today()

        # collect all non-null candidate dates to validate them all
        all_input_dates: List[date] = [d for d in incoming if d is not None]
        if explicit_last is not None and not any(incoming):
            all_input_dates = [explicit_last]

        # rule 1: no future dates for any provided date
        for d in all_input_dates:
            if d > today:
                raise BfFeedingDomainException('One or more dates are in the future. Please use today or past dates only.')

        # rule 2: no duplicate date entries in the provided payload
        iso_vals = [d.isoformat() for d in all_input_dates]
        if len(iso_vals) != len(set(iso_vals)):
            raise BfFeedingDomainException('Duplicate dates are not allowed.')

        # Fetch existing dates and validate additions/immutability rules
        existing_rows = self.ch_repo.fetch_child_details_bf_display_by_chr_id(chr_id) or []
        existing_dates: List[date] = []
        if isinstance(existing_rows, list):
            rows = sorted(existing_rows, key=lambda r: (r.get('visit_id') or 0))
            for row in rows[:5]:
                cd = row.get('check_date')
                parsed = self._parse_single(cd)
                if parsed:
                    existing_dates.append(parsed)

        # Decide check_date and enforce rules
        if existing_dates:
            new_non_null = [d for d in incoming if d is not None]
            if len(new_non_null) < len(existing_dates):
                raise BfFeedingDomainException('Cannot remove previously recorded check dates. To modify existing entries, edit the original record.')

            # prefix = new_non_null[: len(existing_dates)]
            # if prefix != existing_dates:
            #     raise BfFeedingDomainException('Existing check dates may not be modified. To change them, edit the original record.')
            prefix = new_non_null[: len(existing_dates)]
            if len(new_non_null) < len(existing_dates) or prefix != existing_dates:
                raise BfFeedingDomainException(
                    'Existing check dates may not be modified. To change them, edit the original record.'
                )

            if len(new_non_null) == len(existing_dates):
                raise BfFeedingDomainException('No changes detected — the submitted dates match existing records.')

            if len(new_non_null) > len(existing_dates):
                new_entries = new_non_null[len(existing_dates):]
                last_existing = existing_dates[-1]
                prev = last_existing
                # rule 4: newly entered dates must be strictly after the previous dates
                # and strictly increasing among themselves
                # also disallow duplicates against existing dates
                seen_existing = {d.isoformat() for d in existing_dates}
                for d in new_entries:
                    if d.isoformat() in seen_existing:
                        raise BfFeedingDomainException('Duplicate dates are not allowed.')
                    if d <= prev:
                        raise BfFeedingDomainException('Newly added check dates must be after the previously recorded date.')
                    prev = d
                check_date = new_entries[-1]
        else:
            new_non_null = [d for d in incoming if d is not None]
            # rule 4 (first entry set): ensure strictly increasing sequence
            for i in range(1, len(new_non_null)):
                if new_non_null[i] <= new_non_null[i-1]:
                    raise BfFeedingDomainException('Breastfeeding check dates must be in chronological order and each date must be later than the previous one.')
            check_date = new_non_null[-1] if new_non_null else (explicit_last or None)

        # rule 5: only up to 5 entries allowed (enforced by input slots length)
        if len([d for d in incoming if d is not None]) > 5:
            raise BfFeedingDomainException('Only up to 5 breastfeeding check dates are allowed.')

        if not check_date:
            raise BfFeedingDomainException('No valid check date to save.')

        return check_date
