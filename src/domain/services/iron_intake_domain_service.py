from __future__ import annotations

from typing import Dict, Any
from decimal import Decimal

import logging

from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.exceptions.iron_intake_domain_exception import IronIntakeDomainException
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository


class IronIntakeDomainService:
    """Domain validation for iron supplement completion records.

    Rules:
    - Dates must not be in the future (Manila tz via DateAndTimeUtility).
    - `date_completed` cannot be set unless `date_started` exists (either in payload or stored record).
    - If an existing record has `date_started`, do not allow inserting another `date_started`.
    - If an existing record has `date_completed`, do not allow inserting additional dates.
    - If both dates are provided in payload, validate cross-constraints.
    - Date parsing delegated to `DateAndTimeUtility`.
    """

    def __init__(self, ch_repo: IChildHealthRecordRepository):
        self.ch_repo = ch_repo
        self.logger = logging.getLogger(__name__)

    def validate_and_prepare(self, chr_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})

        # parse dates with infra utility
        ds_raw = data.get("date_started") or data.get("date_iron_started")
        dc_raw = data.get("date_completed") or data.get("date_iron_completed")

        parsed_ds = None
        parsed_dc = None
        today = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date())

        self.logger.debug("Validating iron intake payload for chr_id=%s payload=%s", chr_id, payload)

        if ds_raw:
            parsed_ds = DateAndTimeUtility.to_date(ds_raw)
            if not parsed_ds:
                self.logger.warning("Invalid date format for date_started: %s", ds_raw)
                raise IronIntakeDomainException("Invalid date. Use YYYY-MM-DD")
            if parsed_ds > today:
                self.logger.warning("date_started in future: %s (today=%s)", parsed_ds, today)
                raise IronIntakeDomainException("Date cannot be in the future")

        if dc_raw:
            parsed_dc = DateAndTimeUtility.to_date(dc_raw)
            if not parsed_dc:
                self.logger.warning("Invalid date format for date_completed: %s", dc_raw)
                raise IronIntakeDomainException("Invalid date. Use YYYY-MM-DD")
            if parsed_dc > today:
                self.logger.warning("date_completed in future: %s (today=%s)", parsed_dc, today)
                raise IronIntakeDomainException("Date cannot be in the future")

        # Do not allow empty/null insertion: at least a start date or completion must be provided.
        # (completion without start is allowed only when an existing start exists; that rule is enforced later)
        if not ds_raw and not dc_raw:
            self.logger.warning("Empty submission detected for chr_id=%s", chr_id)
            raise IronIntakeDomainException("No data provided. Please include a start date to create or update a record.")

        # load existing record to enforce uniqueness/sequence rules
        existing = None
        try:
            existing = self.ch_repo.fetch_iron_supplement_completion_by_chr_id(chr_id)
        except Exception:
            # repository errors are surfaced as-is to be handled upstream
            existing = None

        self.logger.debug("Existing iron intake record for chr_id=%s: %s", chr_id, existing)

        existing_ds = None
        existing_dc = None
        # existing may be a list of rows, a single dict, or None. normalize to a dict if present
        self.logger.debug("Existing data for chr_id=%s: %s", chr_id, existing)
        existing_data = None
        if existing:
            if isinstance(existing, (list, tuple)):
                if len(existing) > 0:
                    existing_data = existing[0]
                else:
                    # treat empty list as no existing record
                    existing_data = None
            elif isinstance(existing, dict):
                existing_data = existing
            else:
                # try to coerce to dict-like (e.g., namedtuple or row)
                try:
                    existing_data = dict(existing)
                except Exception:
                    existing_data = None

        if existing_data:
            # handle both date objects and string dates
            ds_val = existing_data.get("date_started")
            dc_val = existing_data.get("date_completed")
            from datetime import date as _date

            if ds_val:
                if isinstance(ds_val, _date):
                    existing_ds = ds_val
                else:
                    existing_ds = DateAndTimeUtility.to_date(ds_val)
            if dc_val:
                if isinstance(dc_val, _date):
                    existing_dc = dc_val
                else:
                    existing_dc = DateAndTimeUtility.to_date(dc_val)

        # If existing record has both dates completed, disallow any further inserts
        if existing_dc is not None and existing_ds is not None:
            self.logger.warning("Attempt to insert when existing record already completed for chr_id=%s", chr_id)
            raise IronIntakeDomainException("Existing iron intake record is already completed; cannot add another entry")

        # If payload attempts to add date_started but one already exists, allow only
        # when it's paired with date_completed and the incoming date_started matches
        # the existing date_started. This permits adding the missing date_completed
        # while ensuring the start date is the same as recorded.
        if parsed_ds and existing_ds is not None:
            if not parsed_dc:
                self.logger.warning("Attempt to insert duplicate start date for chr_id=%s without paired completion", chr_id)
                raise IronIntakeDomainException("Start date already recorded. To add completion, submit both start and completion dates that match the recorded start.")
            # both parsed_ds and parsed_dc present; ensure incoming start matches existing
            if parsed_ds != existing_ds:
                self.logger.warning("Incoming start date (%s) does not match existing (%s) for chr_id=%s", parsed_ds, existing_ds, chr_id)
                raise IronIntakeDomainException("Start date does not match the recorded start; cannot pair with completion.")
            # allowed paired re-insert — log metric/info
            self.logger.info("Paired re-insert allowed for chr_id=%s; start matches existing. Recording completion.", chr_id)

        # If payload includes date_completed but neither payload date_started nor existing date_started, disallow
        if parsed_dc and (not parsed_ds) and (existing_ds is None):
            self.logger.warning("Attempt to insert completion without start for chr_id=%s", chr_id)
            raise IronIntakeDomainException("Cannot record completion without an existing start date")

        # If existing_dc already present, disallow adding date_completed
        if parsed_dc and existing_dc is not None:
            self.logger.warning("Attempt to insert duplicate date_completed for chr_id=%s", chr_id)
            raise IronIntakeDomainException("date_completed already exists for this record; cannot insert another date_completed")

        # If both provided ensure start <= completed
        if parsed_ds and parsed_dc:
            if parsed_dc < parsed_ds:
                self.logger.warning("date_completed < date_started (%s < %s) for chr_id=%s", parsed_dc, parsed_ds, chr_id)
                raise IronIntakeDomainException("date_completed cannot be earlier than date_started")

        # Normalize to date objects for repository
        if parsed_ds:
            data["date_started"] = parsed_ds
        if parsed_dc:
            data["date_completed"] = parsed_dc

        self.logger.debug("Normalized iron intake payload for chr_id=%s: %s", chr_id, data)

        return data
