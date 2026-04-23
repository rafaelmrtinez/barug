from datetime import date
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


class MaternalScheduleDomainService:
    @staticmethod
    def ensure_no_pending_maternal_visits(repository, mhr_id: int):
        """Raise MaternalHealthRecordException if most recent maternal_visit_schedule is PENDING and still within scheduled date."""
        rows = repository.fetch_maternal_visit_statuses_by_mhr_id(mhr_id)
        if not rows:
            return
        
        # Get the most recent schedule (first row, assuming ordered by date DESC)
        most_recent = rows[0]
        status_name = (most_recent.get('status_name') or '').upper()
        scheduled_date = most_recent.get('scheduled_date')
        
        # Only block if status is PENDING and the scheduled date is today or in the future
        if status_name == 'PENDING' and scheduled_date:
            today = date.today()
            # Convert to date if it's a datetime object
            if hasattr(scheduled_date, 'date'):
                scheduled_date = scheduled_date.date()
            
            if scheduled_date >= today:
                raise MaternalHealthRecordException('Pending schedule exists for this maternal record.')

    @staticmethod
    def ensure_no_pending_postpartum_visits(repository, mhr_id: int):
        """Raise MaternalHealthRecordException if most recent postpartum_visit_schedule is PENDING and still within scheduled date."""
        rows = repository.fetch_postpartum_visit_statuses_by_mhr_id(mhr_id)
        if not rows:
            return
        
        # Get the most recent schedule (first row, assuming ordered by date DESC)
        most_recent = rows[0]
        status_name = (most_recent.get('status_name') or '').upper()
        scheduled_date = most_recent.get('scheduled_date')
        
        # Only block if status is PENDING and the scheduled date is today or in the future
        if status_name == 'PENDING' and scheduled_date:
            today = date.today()
            # Convert to date if it's a datetime object
            if hasattr(scheduled_date, 'date'):
                scheduled_date = scheduled_date.date()
            
            if scheduled_date >= today:
                raise MaternalHealthRecordException('Pending postpartum schedule exists for this maternal record.')
