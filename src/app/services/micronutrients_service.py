from typing import Any, Dict, Optional
import logging

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility

LOG = logging.getLogger(__name__)


class MicroNutrientsValidationException(Exception):
    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class MicroNutrientsService:
    """Service to validate and persist micronutrients data.

    Replicates the behavior of `MicroNutrientsForm.clean()` but in a
    service layer and suitable for DI and unit testing.
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mhr_id = payload.get("mhr_id")
        if not mhr_id:
            raise MicroNutrientsValidationException("Missing mhr_id.", errors={"mhr_id": ["Missing mhr_id."]})

        # Fetch existing micronutrients to allow using initial values where needed
        try:
            existing = self.repository.fetch_micronutrients_by_mhr_id(int(mhr_id))
        except Exception:
            LOG.exception("Failed to fetch existing micronutrients for mhr %s", mhr_id)
            existing = None

        iron_start = payload.get("iron_folic_start")
        iron_end = payload.get("iron_folic_end")
        deworm = payload.get("deworming_date")

        # Determine if there is at least one allowed date provided (submitted or initial)
        def has_value(val, field_name):
            if val:
                return True
            # fallback to initial from existing record
            if existing and isinstance(existing, dict):
                key_map = {
                    "iron_folic_start": "iron_start_date",
                    "iron_folic_end": "iron_end_date",
                    "deworming_date": "deworming_date",
                }
                existing_key = key_map.get(field_name)
                if existing_key and existing.get(existing_key) is not None:
                    return True
            return False

        if not (has_value(iron_start, "iron_folic_start") or has_value(deworm, "deworming_date")):
            raise MicroNutrientsValidationException(
                "Please provide at least one date: either 'Iron w/ Folic Acid (start)' or 'Deworming' before saving. If neither applies, add a brief note explaining why.",
                errors={"__all__": ["Please provide at least one date: either 'Iron w/ Folic Acid (start)' or 'Deworming' before saving. If neither applies, add a brief note explaining why."]},
            )

        # get PH current date
        try:
            ph_current = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date())
        except Exception:
            ph_current = None

        def coerce_date(val, field_label):
            if val is None or val == "":
                return None
            # if already date-like
            if hasattr(val, 'strftime'):
                return val
            try:
                return DateAndTimeUtility.parse_date(val)
            except Exception:
                raise MicroNutrientsValidationException(f"{field_label}: the provided date is invalid. Please use YYYY-MM-DD.", errors={field_label: [f"{field_label}: the provided date is invalid. Please use YYYY-MM-DD."]})

        # Coerce values (use submitted values only; initial values are used earlier for presence checks)
        s_parsed = coerce_date(iron_start, "Iron w/ Folic Acid (start)")
        e_parsed = coerce_date(iron_end, "Iron w/ Folic Acid (completed)")
        d_parsed = coerce_date(deworm, "Deworming")

        # Validate dates against PH current (must be strictly before)
        # if ph_current:
        #     for parsed, label in ((s_parsed, "Iron w/ Folic Acid (start)"), (e_parsed, "Iron w/ Folic Acid (completed)"), (d_parsed, "Deworming")):
        #         if parsed is None:
        #             continue
        #         if parsed >= ph_current:
        #             raise MicroNutrientsValidationException(f"{label}: today's date and future dates are not allowed. Please enter a date before {ph_current}.", errors={label: [f"{label}: today's date and future dates are not allowed. Please enter a date before {ph_current}."]})

        # If there is an end date but no start (submitted or initial) -> error
        existing_start = existing.get("iron_start_date") if existing and isinstance(existing, dict) else None
        if e_parsed and not (s_parsed or existing_start):
            raise MicroNutrientsValidationException("Please enter the Iron w/ Folic Acid (start) date before providing the completed date.", errors={"iron_folic_start": ["Please enter the Iron w/ Folic Acid (start) date before providing the completed date."]})

        # If both start and end present ensure chronological order
        if s_parsed and e_parsed and e_parsed < s_parsed:
            raise MicroNutrientsValidationException("Iron w/ Folic Acid (completed) cannot be earlier than the start date. Please correct the dates.", errors={"iron_folic_end": ["Iron w/ Folic Acid (completed) cannot be earlier than the start date. Please correct the dates."]})

        return {
            "mhr_id": int(mhr_id),
            "iron_folic_start": s_parsed,
            "iron_folic_end": e_parsed,
            "deworming_date": d_parsed,
        }

    def save_micronutrients(self, payload: Dict[str, Any], staff_id: int):
        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        cleaned = self.validate(payload)
        try:
            res = self.repository.insert_micronutrients(
                mhr_id=cleaned["mhr_id"],
                staff_id=staff_id,
                iron_started=cleaned.get("iron_folic_start"),
                iron_completed=cleaned.get("iron_folic_end"),
                deworming_started=cleaned.get("deworming_date"),
            )
            return res
        except MaternalHealthRecordException:
            raise
        except Exception:
            LOG.exception("Failed to persist micronutrients for mhr_id=%s", payload.get("mhr_id"))
            raise ServiceExecutionException("Failed to persist micronutrients.")
