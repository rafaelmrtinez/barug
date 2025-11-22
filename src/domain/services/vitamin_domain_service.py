from typing import List, Optional, Set

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.domain.exceptions.vitamin_domain_exception import VitaminDomainException


class VitaminDomainService:
    """Enforces Vitamin A business rules.

    Rules implemented:
    - Do not allow None values to be persisted.
    - Hierarchical insertions: stage 2 requires stage 1; stage 3 requires stages 1 and 2.
    - Check against database existing stages and disallow re-insertion of existing stages.
    - Maximum of 3 insertions overall.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository):
        self._repo = ch_repo

    def _normalize_existing_stages(self, stages) -> Set[int]:
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
        try:
            return set(int(s) for s in stages)
        except Exception:
            return set()

    def validate_and_select_stage(self, child_health_record_id: int, requested_stages: Optional[List[int]] = None, stage_id: Optional[int] = None) -> int:
        """Validate incoming request and return the single stage id to apply.

        Raises `VitaminDomainException` with friendly messages on validation failure.
        """
        # Do not accept None as an actionable input
        if stage_id is None and not requested_stages:
            raise VitaminDomainException("No Vitamin A stage provided")

        # Fetch existing stages from DB to apply rules
        existing = self._repo.fetch_vitamin_by_chr_id(child_health_record_id) or []
        existing_set = self._normalize_existing_stages(existing)

        # Rule: maximum of 3 insertions overall
        if len(existing_set) >= 3:
            raise VitaminDomainException("All Vitamin A stages are already recorded; no further insertions allowed")

        # Resolve stage_to_apply
        if stage_id is not None:
            try:
                stage_to_apply = int(stage_id)
            except Exception:
                raise VitaminDomainException("Invalid stage id")
        else:
            # Use the highest requested stage
            try:
                stage_to_apply = int(max(requested_stages))
            except Exception:
                raise VitaminDomainException("Invalid requested vitamin stages")

        if stage_to_apply not in (1, 2, 3):
            raise VitaminDomainException("Vitamin stage must be 1, 2, or 3")

        # If the requested stage already exists -> disallow re-insertion
        if stage_to_apply in existing_set:
            raise VitaminDomainException(f"Vitamin A stage {stage_to_apply} already exists and cannot be re-added")

        # Hierarchical rules
        if stage_to_apply == 2:
            # stage 2 requires stage 1 either existing or included in incoming request
            if 1 not in existing_set and (not requested_stages or 1 not in requested_stages):
                raise VitaminDomainException("Stage 2 requires Stage 1 to be present or selected")

        if stage_to_apply == 3:
            # stage 3 requires stages 1 and 2
            missing = []
            if 1 not in existing_set and (not requested_stages or 1 not in requested_stages):
                missing.append("1")
            if 2 not in existing_set and (not requested_stages or 2 not in requested_stages):
                missing.append("2")
            if missing:
                raise VitaminDomainException("Stage 3 requires stages 1 and 2 to be present or selected")

        # Check that applying this new stage will not push beyond 3 total stages
        projected_total = len(existing_set) + 1
        if projected_total > 3:
            raise VitaminDomainException("Cannot add more than three Vitamin A stages")

        # All checks passed
        return stage_to_apply
