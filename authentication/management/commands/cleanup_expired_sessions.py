import logging
from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.conf import settings
from authentication.db import call_staff_logout, call_staff_logout_with_time
from datetime import timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up expired sessions and log them out in the database'

    def handle(self, *args, **options):
        """
        Find all expired sessions and log them out properly.
        This is useful for cleaning up sessions that expired before the middleware was added.
        """
        timeout_seconds = getattr(settings, 'SESSION_COOKIE_AGE', 28800)  # 8 hours
        expired_count = 0
        logged_out_count = 0
        
        self.stdout.write(f"Checking for expired sessions (timeout: {timeout_seconds}s / {timeout_seconds/3600}h)...")
        
        # Get all active sessions
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            try:
                data = session.get_decoded()
                auth = data.get('auth')
                last_activity_str = data.get('last_activity')
                
                if auth and last_activity_str:
                    try:
                        last_activity = timezone.datetime.fromisoformat(last_activity_str)
                        if not timezone.is_aware(last_activity):
                            last_activity = timezone.make_aware(last_activity)
                        
                        time_since_activity = (timezone.now() - last_activity).total_seconds()
                        
                        if time_since_activity > timeout_seconds:
                            # Session expired - log it out
                            login_log_id = auth.get('login_log_id')
                            staff_id = auth.get('staff_id')
                            
                            if login_log_id and staff_id:
                                try:
                                    # Calculate actual logout time
                                    actual_logout_time = last_activity + timedelta(seconds=timeout_seconds)
                                    call_staff_logout_with_time(login_log_id, staff_id, "cleanup_script", actual_logout_time)
                                    logged_out_count += 1
                                    self.stdout.write(
                                        self.style.SUCCESS(
                                            f"Logged out staff_id={staff_id}, login_log_id={login_log_id} at {actual_logout_time}"
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to logout session: {e}")
                            
                            # Delete the session
                            session.delete()
                            expired_count += 1
                            
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid last_activity format in session: {e}")
                        
            except Exception as e:
                logger.error(f"Error processing session: {e}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete: {expired_count} expired sessions removed, {logged_out_count} logged out in database"
            )
        )
