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
from notifications.service import notify_user, PERSON

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
        print(f"DTO {dto}")
        # Delegate to repository
        try:
            res = self.repo.add_child_visit_schedule(
                p_child_record_id=dto.child_record_id,
                p_schedule_date=dto.schedule_date,
                p_schedule_time=dto.schedule_time,
                p_created_by_id=created_by_id,
                p_visit_purpose=purpose,
                p_notes=notes,
            )

            # After persistence succeeded, attempt to notify the mother (person_id)
            try:
                mother_id = None
                # prefer explicit helper if available
                if hasattr(self.repo, 'fetch_mother_id_by_chr_id'):
                    try:
                        mother_id = self.repo.fetch_mother_id_by_chr_id(dto.child_record_id)
                    except Exception:
                        logger.exception('fetch_mother_id_by_chr_id failed for child_record_id=%s', dto.child_record_id)
                else:
                    # fallback: try to extract from the richer record info
                    try:
                        info = None
                        if hasattr(self.repo, 'fetch_child_health_record_info_by_chr_id'):
                            info = self.repo.fetch_child_health_record_info_by_chr_id(dto.child_record_id)
                        # repo helpers sometimes return a list of rows
                        if isinstance(info, list):
                            info = info[0] if info else None
                        if info and isinstance(info, dict):
                            mother_id = info.get('mother_id') or info.get('mother_person_id') or info.get('mother')
                    except Exception:
                        logger.exception('fetch_child_health_record_info_by_chr_id failed for child_record_id=%s', dto.child_record_id)

                if mother_id:
                    # format date/time for human-friendly 12-hour representation
                    date_obj = dto.schedule_date
                    time_obj = dto.schedule_time
                    date_str = date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj)
                    time_str = time_obj.strftime('%I:%M %p') if hasattr(time_obj, 'strftime') else str(time_obj)
                    title = 'Child health visit scheduled'
                    body = f'Visit scheduled on {date_str} at {time_str} — {purpose}'
                    deep_link = "/(bhw)/(tabs)/postpartum"
                    try:
                        notify_user(user_type_id=PERSON, person_id=mother_id, staff_id=None, title=title, body=body, deep_link=deep_link)
                    except Exception:
                        logger.exception('Failed to send child visit notification to person_id=%s', mother_id)
                else:
                    logger.info('No mother_id found for child_record_id=%s; skipping notification', dto.child_record_id)
            except Exception:
                logger.exception('Error while resolving mother_id for child_record_id=%s', dto.child_record_id)

            return res
        except Exception as e:
            logger.exception('Failed to create visit schedule: %s', e)
            raise
