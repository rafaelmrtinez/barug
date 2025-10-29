
from typing import Optional
from datetime import date as _date, datetime as _datetime

from maternal.repository import MaternalHealthRecordRepository
from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException
from src.domain.services.maternal_schedule_domain_service import MaternalScheduleDomainService


class MaternalScheduleService:
    """Application service to orchestrate prenatal/postpartum scheduling.

    This layer is intentionally thin: it validates/coerces parameters when
    necessary and delegates persistence to the repository.
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repo = repository

    def schedule_prenatal(self, mhr_id: int, date, time, staff_id: int, purpose: str, notes: Optional[str]):
        # Validate: date must not be in the past
        try:
            # disallow past dates/times: combine date+time and compare to now
            try:
                scheduled_dt = _datetime.combine(date, time)
            except Exception:
                # fallback to date-only validation
                scheduled_dt = None

            now = _datetime.now()
            if scheduled_dt is not None and scheduled_dt < now:
                raise MaternalHealthRecordException('Cannot schedule a prenatal visit in the past.')
            if scheduled_dt is None and date < _date.today():
                raise MaternalHealthRecordException('Cannot schedule a prenatal visit in the past.')

            # Domain validation: ensure no other pending maternal visits exist
            MaternalScheduleDomainService.ensure_no_pending_maternal_visits(self.repo, mhr_id)

            return self.repo.insert_maternal_visit_schedule(mhr_id, date, time, staff_id, purpose, notes)
        except MaternalHealthRecordException:
            raise

    def schedule_postpartum(self, mhr_id: int, date, time, staff_id: int, visit: str, purpose: str):
        try:
            # disallow past dates/times
            try:
                scheduled_dt = _datetime.combine(date, time)
            except Exception:
                scheduled_dt = None

            now = _datetime.now()
            if scheduled_dt is not None and scheduled_dt < now:
                raise MaternalHealthRecordException('Cannot schedule a postpartum visit in the past.')
            if scheduled_dt is None and date < _date.today():
                raise MaternalHealthRecordException('Cannot schedule a postpartum visit in the past.')

            # Domain validation: ensure no other pending postpartum visits exist
            MaternalScheduleDomainService.ensure_no_pending_postpartum_visits(self.repo, mhr_id)

            # repository expects (mhr_id, date, time, staff_id, purpose, notes)
            # map: visit -> purpose (short label), purpose -> notes (description)
            return self.repo.insert_postpartum_visit_schedule(mhr_id, date, time, staff_id, visit, purpose)
        except MaternalHealthRecordException:
            raise
