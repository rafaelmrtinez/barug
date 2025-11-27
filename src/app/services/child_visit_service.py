import logging
from decimal import Decimal
from datetime import date
from typing import Any, Dict

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.app.transfer_objects.request.child_health_version_two.child_monitoring_log import ChildMonitoringLog
from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
from src.domain.services.child_visit_domain_service import ChildVisitDomainService
from src.domain.exceptions.child_visit_domain_exception import ChildVisitDomainException
from typing import Optional, Any

logger = logging.getLogger(__name__)


class ChildVisitService:
    """Service to validate, normalize and persist child visit (child monitoring log) entries.

    This moves the validation and normalization logic out of forms into a testable
    service that the API can use directly.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository, domain_service: ChildVisitDomainService, child_monitoring_query: Optional[Any] = None):
        self._repo = ch_repo
        self._domain = domain_service
        # optional query provider for read-only monitoring queries (injected by container)
        self._monitoring_query = child_monitoring_query

    def process_and_insert(self, chr_id: int, staff_id: int, staff_role: str, payload: Dict[str, Any]) -> Any:
        """Validate payload, build ChildMonitoringLog and insert via repository.

        Raises ChildHealthRecordException on validation errors.
        Returns whatever the repository insert returns on success.
        """
        # copy and normalize
        data = dict(payload or {})
        data.pop('form_type', None)
        # Normalize common aliases from client payloads
        if 'temperature' in data and 'temp' not in data:
            data['temp'] = data.pop('temperature')

        # delegate domain validation/normalization (role-aware)
        try:
            normalized = self._domain.validate_and_normalize(data, role=staff_role)
        except ChildVisitDomainException as dv:
            # log and re-raise domain exception so API layer can handle it
            logger.warning('ChildVisit domain validation failed: %s', dv.message)
            raise

        # If user is midwife, domain normalization intentionally returns only findings.
        # In that case update the existing monitoring row via the dedicated repo method.
        if staff_role and str(staff_role).lower() == 'midwife':
            # need the monitoring id from payload (several possible keys)
            monitor_id = (
                data.get('child_monitoring_id')
                or data.get('monitoring_id')
                or data.get('child_monitor_id')
                or data.get('id')
            )
            # If no monitoring id provided, try to auto-lookup the latest monitoring id
            # for this child record using the injected query helper.
            if not monitor_id and getattr(self, '_monitoring_query', None):
                try:
                    latest = self._monitoring_query.fetch_latest_by_child_record_id(chr_id)
                    if latest and latest.get('child_monitoring_id'):
                        monitor_id = latest.get('child_monitoring_id')
                        logger.info('Auto-selected latest monitoring id %s for midwife update', monitor_id)
                except Exception as e:
                    logger.warning('Failed to auto-lookup latest monitoring id: %s', e)
            if not monitor_id:
                raise ChildVisitDomainException('monitoring_id_required', code='monitoring_id_required')

            findings = normalized.get('findings')
            notes = normalized.get('notes')
            # call midwife-specific update; notes intentionally excluded per spec (pass None)
            res = self._repo.insert_child_monitoring_log_midwife(
                p_child_record_id=chr_id,
                p_child_monitoring_id=monitor_id,
                p_findings=findings,
                p_notes=notes,
                p_performed_by_id=staff_id,
            )
            logger.info('Midwife updated child monitoring log: %s', res)
            return res

        # date override to current PH date for normal (non-midwife) inserts
        try:
            today = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()) or date.today()
        except Exception:
            today = date.today()
        normalized['date'] = today

        # Build transfer object and persist as a new monitoring log
        log = ChildMonitoringLog(**normalized)
        res = self._repo.insert_child_monitoring_log(log=log, chr_id=chr_id, staff_id=staff_id)
        logger.info('Inserted child monitoring log: %s', res)
        return res
