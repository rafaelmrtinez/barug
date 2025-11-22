from typing import List, Optional, Set

import logging

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.domain.exceptions.vitamin_domain_exception import VitaminDomainException
from src.infra.utilities.message_catalog import MessageCatalog

logger = logging.getLogger(__name__)


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
            msg = MessageCatalog.translate("no_input")
            logger.warning("Vitamin validation failed: %s (chr=%s)", msg, child_health_record_id)
            raise VitaminDomainException(msg, code="no_input")

        # Fetch existing stages from DB to apply rules
        existing = self._repo.fetch_vitamin_by_chr_id(child_health_record_id) or []
        existing_set = self._normalize_existing_stages(existing)

        # Rule: maximum of 3 insertions overall
        if len(existing_set) >= 3:
            msg = MessageCatalog.translate("all_recorded")
            logger.warning("Vitamin validation failed: %s (chr=%s) existing=%s", msg, child_health_record_id, existing_set)
            raise VitaminDomainException(msg, code="all_recorded")

        # Resolve stage_to_apply
        if stage_id is not None:
            try:
                stage_to_apply = int(stage_id)
            except Exception:
                msg = MessageCatalog.translate("invalid_stage_id")
                logger.warning("Vitamin validation failed: %s (chr=%s) incoming=%s", msg, child_health_record_id, stage_id)
                raise VitaminDomainException(msg, code="invalid_stage_id")
        else:
            # Use the highest requested stage
            try:
                stage_to_apply = int(max(requested_stages))
            except Exception:
                msg = MessageCatalog.translate("invalid_requested_stages")
                logger.warning("Vitamin validation failed: %s (chr=%s) incoming=%s", msg, child_health_record_id, requested_stages)
                raise VitaminDomainException(msg, code="invalid_requested_stages")

        if stage_to_apply not in (1, 2, 3):
            msg = MessageCatalog.translate("invalid_stage_value")
            logger.warning("Vitamin validation failed: %s (chr=%s) incoming=%s", msg, child_health_record_id, stage_to_apply)
            raise VitaminDomainException(msg, code="invalid_stage_value")

        # If the requested stage already exists -> disallow re-insertion
        if stage_to_apply in existing_set:
            msg = MessageCatalog.translate("already_exists", stage=stage_to_apply)
            logger.warning("Vitamin validation failed: %s (chr=%s) existing=%s", msg, child_health_record_id, existing_set)
            raise VitaminDomainException(msg, code="already_exists")

        # Hierarchical rules
        if stage_to_apply == 2:
            # stage 2 requires stage 1 either existing or included in incoming request
            if 1 not in existing_set and (not requested_stages or 1 not in requested_stages):
                msg = MessageCatalog.translate("stage2_requires_1")
                logger.warning("Vitamin validation failed: %s (chr=%s) existing=%s incoming=%s", msg, child_health_record_id, existing_set, requested_stages)
                raise VitaminDomainException(msg, code="stage2_requires_1")

        if stage_to_apply == 3:
            # stage 3 requires stages 1 and 2
            missing = []
            if 1 not in existing_set and (not requested_stages or 1 not in requested_stages):
                missing.append("1")
            if 2 not in existing_set and (not requested_stages or 2 not in requested_stages):
                missing.append("2")
            if missing:
                msg = MessageCatalog.translate("stage3_requires_1_2")
                logger.warning("Vitamin validation failed: %s (chr=%s) existing=%s incoming=%s", msg, child_health_record_id, existing_set, requested_stages)
                raise VitaminDomainException(msg, code="stage3_requires_1_2")

        # Check that applying this new stage will not push beyond 3 total stages
        projected_total = len(existing_set) + 1
        if projected_total > 3:
            msg = MessageCatalog.translate("max_three")
            logger.warning("Vitamin validation failed: %s (chr=%s) existing=%s incoming=%s", msg, child_health_record_id, existing_set, requested_stages)
            raise VitaminDomainException(msg, code="max_three")

        # All checks passed
        logger.info("Vitamin validation succeeded: stage=%s (chr=%s) existing=%s incoming=%s", stage_to_apply, child_health_record_id, existing_set, requested_stages)
        return stage_to_apply
