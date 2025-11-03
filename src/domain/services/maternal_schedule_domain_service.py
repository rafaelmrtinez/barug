from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


class MaternalScheduleDomainService:
    @staticmethod
    def ensure_no_pending_maternal_visits(repository, mhr_id: int):
        """Raise MaternalHealthRecordException if any maternal_visit_schedule for mhr_id has status PENDING."""
        rows = repository.fetch_maternal_visit_statuses_by_mhr_id(mhr_id)
        for r in (rows or []):
            status_name = (r.get('status_name') or '').upper()
            if status_name == 'PENDING':
                # Use existing SQL error code reference in message for clarity
                raise MaternalHealthRecordException('Pending schedule exists for this maternal record.')

    @staticmethod
    def ensure_no_pending_postpartum_visits(repository, mhr_id: int):
        """Raise MaternalHealthRecordException if any postpartum_visit_schedule for mhr_id has status PENDING."""
        rows = repository.fetch_postpartum_visit_statuses_by_mhr_id(mhr_id)
        for r in (rows or []):
            status_name = (r.get('status_name') or '').upper()
            if status_name == 'PENDING':
                raise MaternalHealthRecordException('Pending postpartum schedule exists for this maternal record.')
