
from typing import Optional
from datetime import date as _date, datetime as _datetime

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.app.contracts.maternal_schedule_service import IMaternalScheduleService
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.domain.services.maternal_schedule_domain_service import MaternalScheduleDomainService
from notifications.service import NotifierService, NotifyTarget, STAFF, PERSON
import logging

logger = logging.getLogger(__name__)


class MaternalScheduleService(IMaternalScheduleService):
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

            # Additional safety: check latest prenatal schedule status and disallow
            # creating a new prenatal schedule when the latest prenatal schedule is
            # still pending/active. This duplicates domain intent but provides a
            # clear, user-friendly error at the service boundary.
            # try:
            #     latest_pr_status = self.repo.fetch_latest_prenatal_status_by_mhr_id(mhr_id)
            # except Exception:
            #     raise MaternalHealthRecordException('Unable to validate existing prenatal schedules. Please try again.')

            # if latest_pr_status and int(latest_pr_status.get('status_id') or 0) == 1:
            #     raise MaternalHealthRecordException('A pending prenatal schedule already exists. Complete or cancel it before adding a new prenatal schedule.')

            result = self.repo.insert_maternal_visit_schedule(mhr_id, date, time, staff_id, purpose, notes)

            # Dispatch notification to the staff who created the schedule
            try:
                notifier = NotifierService()
                # Attempt to resolve the patient (person_id) for this maternal record
                try:
                    report_repo = MaternalReportRepository(self.repo.ctx)
                    patient = report_repo.fetch_patient_info(mhr_id)
                    person_id = patient.get('person_id') if patient else None
                except Exception:
                    logger.exception('Failed to fetch patient info for mhr %s', mhr_id)
                    person_id = None

                if person_id is None:
                    logger.info('No person_id found for mhr %s; skipping person notification', mhr_id)
                else:
                    target = NotifyTarget(user_type_id=PERSON, person_id=person_id)
                    title = 'Prenatal schedule created'
                    date_str = date.isoformat() if hasattr(date, 'isoformat') else str(date)
                    time_str = time.strftime('%I:%M %p') if hasattr(time, 'strftime') else str(time)
                    body = f'Prenatal visit scheduled on {date_str} at {time_str} — {purpose}'
                    deep_link = "/(bhw)/(tabs)/postpartum"
                    logger.info("Sending prenatal schedule notification to target=%s title=%s", target, title)
                    try:
                        sent = notifier.notify_user(target=target, title=title, body=body, deep_link=deep_link)
                        logger.info("Prenatal notification sent=%s to target=%s", sent, target)
                    except Exception:
                        logger.exception("Error while sending prenatal notification to target=%s", target)
            except Exception:
                logger.exception('Failed to dispatch prenatal schedule notification (setup)')

            return result
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
            result = self.repo.insert_postpartum_visit_schedule(mhr_id, date, time, staff_id, visit, purpose)

            # Dispatch notification to the staff who created the schedule
            try:
                notifier = NotifierService()
                # Attempt to resolve the patient (person_id) for this maternal record
                try:
                    report_repo = MaternalReportRepository(self.repo.ctx)
                    patient = report_repo.fetch_patient_info(mhr_id)
                    person_id = patient.get('person_id') if patient else None
                except Exception:
                    logger.exception('Failed to fetch patient info for mhr %s', mhr_id)
                    person_id = None

                if person_id is None:
                    logger.info('No person_id found for mhr %s; skipping person notification', mhr_id)
                else:
                    target = NotifyTarget(user_type_id=PERSON, person_id=person_id)
                    title = 'Postpartum schedule created'
                    date_str = date.isoformat() if hasattr(date, 'isoformat') else str(date)
                    time_str = time.strftime('%I:%M %p') if hasattr(time, 'strftime') else str(time)
                    body = f'Postpartum visit scheduled on {date_str} at {time_str} — {visit}'
                    deep_link = "/(bhw)/(tabs)/postpartum"
                    logger.info("Sending postpartum schedule notification to target=%s title=%s", target, title)
                    try:
                        sent = notifier.notify_user(target=target, title=title, body=body, deep_link=deep_link)
                        logger.info("Postpartum notification sent=%s to target=%s", sent, target)
                    except Exception:
                        logger.exception("Error while sending postpartum notification to target=%s", target)
            except Exception:
                logger.exception('Failed to dispatch postpartum schedule notification (setup)')

            return result
        except MaternalHealthRecordException:
            raise
