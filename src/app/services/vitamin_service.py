from typing import List, Optional, Tuple
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


class VitaminService:
    """Service layer for Vitamin A staging and orchestration.

    This encapsulates validation rules previously in the form and
    repository orchestration previously in the API/view.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository):
        self._repo = ch_repo

    def _normalize_existing_stages(self, stages: Optional[list]) -> set:
        if not stages:
            return set()
        if isinstance(stages, list) and stages and isinstance(stages[0], dict):
            out = set()
            for s in stages:
                if s.get("vit_stage_id"):
                    out.add(int(s.get("vit_stage_id")))
                elif s.get("vitamin_a_stage_id"):
                    out.add(int(s.get("vitamin_a_stage_id")))
            return out
        return set(int(s) for s in stages)

    def validate_requested_stages(self, child_health_record_id: int, requested_stages: List[int]) -> Tuple[Optional[int], List[Tuple[str, str]]]:
        """Validate requested stages and return (stage_to_apply, errors).

        Returns (latest_requested_stage, []) when valid, or (None, errors) when invalid.
        Errors are returned as list of tuples: (field_name, message).
        """
        errors: List[Tuple[str, str]] = []

        if not requested_stages:
            return None, []

        existing = self._repo.fetch_vitamin_by_chr_id(child_health_record_id) or []
        existing_set = self._normalize_existing_stages(existing)

        latest_requested_stage = max(requested_stages)

        # Rule 1: all preceding stages must exist or be selected
        for stage in range(1, latest_requested_stage):
            if stage not in existing_set and stage not in requested_stages:
                errors.append((f"vit_a_{latest_requested_stage}", f"Cannot give stage {latest_requested_stage} before completing stage {stage}."))

        # Rule 2: cannot re-add an already existing stage
        if latest_requested_stage in existing_set:
            errors.append((f"vit_a_{latest_requested_stage}", f"Vitamin A stage {latest_requested_stage} already exists in the database."))

        if errors:
            return None, errors

        return latest_requested_stage, []

    def apply_stage(self, child_health_record_id: int, staff_id: int, stage_id: Optional[int] = None, requested_stages: Optional[List[int]] = None) -> bool:
        """Validate (if needed) and persist the vitamin stage via repository.

        - If `stage_id` is provided, it will be persisted directly.
        - If `stage_id` is None, `requested_stages` must be provided and will be
          validated using `validate_requested_stages` to determine the stage to apply.

        Raises `ChildHealthRecordException` on validation errors or missing inputs.
        Returns True on success.
        """
        # Resolve stage from requested_stages when stage_id not provided
        if stage_id is None:
            if not requested_stages:
                raise ChildHealthRecordException("No vitamin stage provided")
            stage_to_apply, errors = self.validate_requested_stages(child_health_record_id, requested_stages)
            if errors:
                # raise with combined messages
                msgs = "; ".join(f"{f}: {m}" for f, m in errors)
                raise ChildHealthRecordException(msgs)
            stage_id = stage_to_apply

        if stage_id is None:
            raise ChildHealthRecordException("No vitamin stage resolved to apply")

        date_given = DateAndTimeUtility.get_current_date()
        print(f"Persisting Vitamin A stage {stage_id} for CHR ID {child_health_record_id} by staff {staff_id} on {date_given}")
        return self._repo.upsert_vitamin_a_stage_by_chr_id(
            p_child_record_id=child_health_record_id,
            staff_id=staff_id,
            stage_id=int(stage_id),
            date_given="2025-11-18",
        )
