from typing import Any, Dict, Optional
import logging

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.form_utils import FormUtils

LOG = logging.getLogger(__name__)


class PlanValidationException(Exception):
    """Raised when plan payload fails validation. Contains optional `errors` dict."""

    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    """Raised for internal/service execution failures not due to validation."""


class PlanService:
    """Service for validating and saving Plans (place of delivery + newborn screening).

    This moves logic out of `PlanForm.clean()` into a testable service layer.
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mhr_id = payload.get("mhr_id")
        if not mhr_id:
            raise PlanValidationException("Missing mhr_id.", errors={"mhr_id": ["Missing mhr_id."]})

        # Fetch existing NBS/plan data: if present make this read-only
        try:
            existing = self.repository.fetch_nbs_data_by_mhr_id(int(mhr_id))
        except Exception:
            LOG.exception("Failed to fetch existing plan data for mhr %s", mhr_id)
            existing = None

        if existing:
            # If the repository already returned plan data, do not allow changes
            raise PlanValidationException(
                "Checklist for latest visit has already been recorded and is read-only.",
                errors={"plan": ["Plan already recorded and read-only."]},
            )

        pod = payload.get("plan_place_of_delivery")
        nbs_plan = payload.get("plan_newborn_screening")

        # If input missing or empty, return friendly error like the form
        if pod is None or (isinstance(pod, str) and pod.strip() == ""):
            raise PlanValidationException(
                "Please specify the planned place of delivery. If not applicable, enter 'N/A'.",
                errors={"plan_place_of_delivery": ["Please specify the planned place of delivery. If not applicable, enter 'N/A'."]},
            )

        # Sanitize using FormUtils
        normalized, err = FormUtils.sanitize_text(pod, "Place of delivery")
        if err:
            raise PlanValidationException(err, errors={"plan_place_of_delivery": [err]})

        # Normalize boolean-like newborn screening value
        if isinstance(nbs_plan, str):
            lower = nbs_plan.lower()
            if lower in ("true", "1", "yes"): nbs_val = True
            elif lower in ("false", "0", "no"): nbs_val = False
            else: nbs_val = False
        else:
            nbs_val = bool(nbs_plan)

        return {
            "mhr_id": int(mhr_id),
            "plan_place_of_delivery": normalized,
            "plan_newborn_screening": nbs_val,
        }

    def save_plan(self, payload: Dict[str, Any], staff_id: int):
        """Validate and persist the plan. Propagates domain exceptions for API layer to map."""
        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        cleaned = self.validate(payload)
        try:
            res = self.repository.insert_plan_and_baseline(
                mhr_id=cleaned["mhr_id"],
                staff_id=staff_id,
                nbs_plan=cleaned.get("plan_newborn_screening"),
                delivery_plan=cleaned.get("plan_place_of_delivery"),
            )
            return res
        except MaternalHealthRecordException:
            # bubble up domain infra exceptions so API can return friendly messages
            raise
        except Exception:
            LOG.exception("Failed to persist plan for mhr_id=%s", payload.get("mhr_id"))
            raise ServiceExecutionException("Failed to persist plan.")
