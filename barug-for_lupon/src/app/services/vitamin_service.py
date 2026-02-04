from typing import List, Optional

from src.app.contracts.vitamin_service import IVitaminService
from src.domain.exceptions.vitamin_domain_exception import VitaminDomainException
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


class VitaminService(IVitaminService):
    """Service layer for Vitamin A staging and orchestration.

    This is a thin orchestrator: it delegates validation to the domain service
    and delegates persistence to the repository.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository, domain_service):
        self._repo = ch_repo
        self._domain = domain_service

    def apply_stage(self, child_health_record_id: int, staff_id: int, stage_id: Optional[int] = None, requested_stages: Optional[List[int]] = None) -> bool:
        """Validate (via domain) and persist the vitamin stage via repository.

        Raises `VitaminDomainException` for domain validation errors and
        `ChildHealthRecordException` for repository-level failures.
        """
        # Let the domain service validate and select a single stage to apply.
        stage_to_apply = self._domain.validate_and_select_stage(
            child_health_record_id=child_health_record_id,
            requested_stages=requested_stages,
            stage_id=stage_id,
        )

        if stage_to_apply is None:
            raise ChildHealthRecordException("No vitamin stage resolved to apply")

        # Ensure we do not persist None values
        date_obj = DateAndTimeUtility.get_current_date()
        # Normalize to ISO string if a date object
        try:
            date_given = date_obj.isoformat()  # type: ignore
        except Exception:
            date_given = str(date_obj)

        return self._repo.upsert_vitamin_a_stage_by_chr_id(
            p_child_record_id=child_health_record_id,
            staff_id=staff_id,
            stage_id=int(stage_to_apply),
            date_given=date_given,
        )
