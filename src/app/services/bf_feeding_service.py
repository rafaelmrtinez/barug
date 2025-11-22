import logging
from datetime import date
from typing import Any, Dict, List, Optional

from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.app.contracts.bf_feeding_service import IBFFeedingService
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.domain.services.bf_feeding_domain_service import BFFeedingDomainService
from src.domain.exceptions.bf_feeding_domain_exception import BfFeedingDomainException

logger = logging.getLogger(__name__)


class BFFeedingService(IBFFeedingService):
    """Service to validate and persist exclusive breastfeeding check dates.

    Moves the validation logic previously in `ChildBreastFeedingForm.clean()` into
    an application service. It returns the repository result on success and
    raises `ChildHealthRecordException` with a helpful message on validation errors.
    """

    def __init__(self, ch_repo: IChildHealthRecordRepository, domain_service: BFFeedingDomainService):
        self._repo = ch_repo
        self._domain = domain_service



    def process_and_insert(self, chr_id: int, staff_id: int, payload: Dict[str, Any]) -> Any:
        """Validate payload and insert a new BF check when appropriate.

        Expects either `exclusive_bf_check_last` or slot fields `exclusive_bf_check_1..5`.
        On validation error raises `ChildHealthRecordException`.
        """
        # Delegate business rule validation and computation to domain service
        try:
            check_date = self._domain.determine_check_date(chr_id=chr_id, payload=payload)
        except BfFeedingDomainException as de:
            # translate domain violation to infra exception expected by API layer
            raise ChildHealthRecordException(de.message)

        # Persist
        is_success = self._repo.insert_bf_check(
            p_child_record_id=chr_id,
            p_assessed_by_id=staff_id,
            p_check_date=check_date,
        )
        if not is_success:
            raise ChildHealthRecordException('Failed to save BF data')
        return is_success
