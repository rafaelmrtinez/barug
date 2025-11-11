"""Service layer for child health visit scheduling.

This service orchestrates validation-free orchestration between the API
and repository. Business rules (beyond straightforward mapping) are not
enforced here per requirements.
"""
from typing import Optional
import logging

from src.app.transfer_objects.request.visit_schedule_request import VisitScheduleRequest
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.app.contracts.child_health_schedule_service import IChildHealthScheduleService
from child_health.utilities.text_normalizer import TextNormalizer

logger = logging.getLogger(__name__)


class ChildHealthScheduleService(IChildHealthScheduleService):
    """Orchestrates creating visit schedules for child health records.

    The service is intentionally thin: it maps the DTO to repository
    parameters and delegates persistence to the repository.
    """

    def __init__(self, repo: ChildHealthRecordRepository):
        self.repo = repo

    def create_visit_schedule(self, dto: VisitScheduleRequest, created_by_id: int) -> Optional[list]:
        """Create a visit schedule row.

        If dto.visit_purpose == 'other', and dto.visit_purpose_other is provided,
        the repository will be called with that text as the visit purpose.
        Returns repository result or None.
        """
        # sanitize/normalize inputs using the TextNormalizer utility
        purpose = TextNormalizer.normalize_text(dto.visit_purpose or '')
        if purpose == 'other' and dto.visit_purpose_other:
            # when user specified 'other', prefer the provided free-text
            purpose = TextNormalizer.normalize_text(dto.visit_purpose_other)

        notes = (dto.visit_notes or '').strip() if dto.visit_notes is not None else None

        # Delegate to repository
        try:
            return self.repo.add_child_visit_schedule(
                p_child_record_id=dto.child_record_id,
                p_schedule_date=dto.schedule_date,
                p_schedule_time=dto.schedule_time,
                p_created_by_id=created_by_id,
                p_visit_purpose=purpose,
                p_notes=notes,
            )
        except Exception as e:
            logger.exception('Failed to create visit schedule: %s', e)
            raise
