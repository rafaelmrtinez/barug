import logging
from decimal import Decimal
from datetime import date
from typing import Any, Dict

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.app.transfer_objects.request.child_health_version_two.child_monitoring_log import ChildMonitoringLog
from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility

logger = logging.getLogger(__name__)


class ChildVisitService:
    """Service to validate, normalize and persist child visit (child monitoring log) entries.

    This moves the validation and normalization logic out of forms into a testable
    service that the API can use directly.
    """

    def __init__(self, ch_repo: ChildHealthRecordRepository):
        self._repo = ch_repo

    def process_and_insert(self, chr_id: int, staff_id: int, payload: Dict[str, Any]) -> Any:
        """Validate payload, build ChildMonitoringLog and insert via repository.

        Raises ChildHealthRecordException on validation errors.
        Returns whatever the repository insert returns on success.
        """
        # copy and normalize
        data = dict(payload or {})
        data.pop('form_type', None)
        # Normalize common aliases from client payloads
        # some clients send 'temperature' while form fields use 'temp'
        if 'temperature' in data and 'temp' not in data:
            data['temp'] = data.pop('temperature')
        # 1) date override to current PH date
        try:
            today = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()) or date.today()
        except Exception:
            today = date.today()
        data['date'] = today

        errors = []

        # 2) age validation
        age_raw = data.get('age')
        if age_raw is None or age_raw == '':
            errors.append(('age', 'Please provide the age.'))
        else:
            try:
                age_val = age_raw if isinstance(age_raw, Decimal) else Decimal(str(age_raw))
            except Exception:
                errors.append(('age', 'Enter a valid age in years (numbers only).'))
            else:
                if age_val >= Decimal('5'):
                    errors.append(('age', 'Age must be less than 5 years for child center visits.'))
                data['age'] = age_val

        # 3) numeric fields: weight, temp, height
        # accept both 'temp' and 'temperature' keys via the normalization above
        logger.debug('Validating numeric fields from data: %s', data)
        for fld, friendly in (('weight', 'weight'), ('temp', 'temperature'), ('height', 'height')):
            val = data.get(fld)
            if val in (None, ''):
                errors.append((fld, f'Please provide the {friendly}.'))
                continue
            try:
                dec = Decimal(str(val))
            except Exception:
                errors.append((fld, f'Enter a valid {friendly} (numbers only).'))
                continue
            if dec <= Decimal('0'):
                errors.append((fld, f'{friendly.capitalize()} must be a positive number.'))
            else:
                data[fld] = dec

        # 4) findings required and sanitized
        findings = data.get('findings')
        if findings in (None, ''):
            errors.append(('findings', 'Please provide the findings.'))
        else:
            findings_norm, findings_err = FormUtils.sanitize_text(str(findings), 'Findings')
            if findings_err:
                errors.append(('findings', findings_err))
            else:
                data['findings'] = findings_norm

        # 5) notes optional, sanitize if present
        notes = data.get('notes')
        if notes in (None, ''):
            data['notes'] = None
        else:
            notes_norm, notes_err = FormUtils.sanitize_text(str(notes), 'Notes')
            if notes_err:
                errors.append(('notes', notes_err))
            else:
                data['notes'] = notes_norm

        # If we have errors, raise a validation exception with details
        if errors:
            # combine into single message; repository/APIs will map to field errors
            msg = '; '.join(f"{f}: {m}" for f, m in errors)
            logger.debug('ChildVisit validation failed: %s', msg)
            raise ChildHealthRecordException(msg)

        # Build transfer object and persist
        log = ChildMonitoringLog(**data)
        res = self._repo.insert_child_monitoring_log(log=log, chr_id=chr_id, staff_id=staff_id)
        logger.info('Inserted child monitoring log: %s', res)
        return res
