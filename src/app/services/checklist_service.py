from typing import Any, Dict, List
import logging

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

LOG = logging.getLogger(__name__)


class CheckListValidationException(Exception):
    """Raised when incoming checklist payload fails validation.

    Attributes:
        errors: optional dict mapping field -> list of error messages
    """

    def __init__(self, message: str = "Validation failed.", errors: Dict[str, List[str]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    """Raised for internal/service execution failures not due to validation."""


class CheckListService:
    """Service responsible for validating and persisting maternal checklist items.

    This reproduces the behavior from `CheckListForm.clean()` but in a testable
    service layer and without depending on Django forms.
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repository = repository

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate incoming payload and return cleaned data.

        Expects `mhr_id` in payload and `symptoms` as an iterable of ids (str|int).
        On validation failure raises `CheckListValidationException` with an
        `errors` dict compatible with the API layer.
        """
        mhr_id = payload.get("mhr_id")
        if not mhr_id:
            raise CheckListValidationException("Missing mhr_id.", errors={"mhr_id": ["Missing mhr_id."]})

        # normalize incoming into a flat list
        incoming = payload.get("symptoms") or []
        if isinstance(incoming, (str, int, bool)):
            incoming = [incoming]

        try:
            incoming_list = [str(v) for v in incoming]
        except Exception:
            raise CheckListValidationException("Invalid symptoms payload.", errors={"symptoms": ["Invalid symptoms payload."]})

        if not incoming_list:
            raise CheckListValidationException("Please select at least one checklist item.", errors={"symptoms": ["Please select at least one checklist item."]})

        # fetch existing checklist items for this maternal record (graceful on error)
        try:
            existing = self.repository.fetch_maternal_checklist_by_mhr_id(int(mhr_id)) or []
        except Exception:
            LOG.exception("Failed to fetch existing checklist for mhr %s", mhr_id)
            existing = []

        # normalize existing ids to strings to compare reliably
        existing_ids: List[str] = []
        for row in existing:
            if isinstance(row, dict):
                val = row.get("checklist_item_id")
            else:
                val = row
            if val is not None:
                existing_ids.append(str(val))

        # determine which incoming items are new (not already recorded)
        new_items = [item for item in incoming_list if item not in existing_ids]

        # If there are no new items selected, produce the same friendly message
        # the form used: list duplicate labels and ask the user to remove them.
        if not new_items:
            duplicates = [item for item in incoming_list if item in existing_ids]
            try:
                items = self.repository.fetch_checklist_items() or []
                choice_map = {str(r.get("checklist_item_id")): (r.get("checklist_name") or "").title() for r in items}
            except Exception:
                choice_map = {}

            dup_labels = [choice_map.get(d, d) for d in duplicates]
            friendly_list = ", ".join(dup_labels)
            message = (
                "Please add at least one new checklist item."
                f"{friendly_list}. Please remove them from your selection or edit the existing checklist if you intended to change their values."
            )
            raise CheckListValidationException(message, errors=message)

        new_items_int: List[int] = []
        for itm in new_items:
            # reject boolean-like values which are unlikely valid ids
            low = itm.lower() if isinstance(itm, str) else None
            if isinstance(itm, bool) or low in ("true", "false"):
                raise CheckListValidationException(
                    f"Invalid checklist item id: {itm}",
                    errors={"symptoms": [f"Invalid checklist item id: {itm}"]},
                )
            try:
                new_items_int.append(int(str(itm).strip()))
            except Exception:
                raise CheckListValidationException(
                    f"Invalid checklist item id: {itm}",
                    errors={"symptoms": [f"Invalid checklist item id: {itm}"]},
                )

        return {"mhr_id": int(mhr_id), "symptoms": new_items_int}

    def save_checklist(self, payload: Dict[str, Any], staff_id: int):
        """Validate and persist checklist items.

        Returns repository response on success or raises exceptions on failure.
        """
        if not self.repository:
            raise ServiceExecutionException("Repository not available for save operation.")

        cleaned = self.validate(payload)
        try:
            res = self.repository.insert_checklist_items(
                mhr_id=cleaned["mhr_id"],
                staff_id=staff_id,
                checklist_items=cleaned["symptoms"],
            )
            return res
        except MaternalHealthRecordException:
            # propagate domain exceptions to API layer
            raise
        except Exception:
            LOG.exception("Failed to persist checklist items for mhr_id=%s", payload.get("mhr_id"))
            raise ServiceExecutionException("Failed to persist checklist items.")
