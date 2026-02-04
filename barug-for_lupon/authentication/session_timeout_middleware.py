import logging
from django.utils import timezone
from datetime import timedelta
from .db import call_staff_logout, call_staff_logout_with_time

logger = logging.getLogger(__name__)

class SessionTimeoutMiddleware:
    """
    Middleware to track session activity and auto-logout expired sessions.
    - Tracks last activity time in session
    - Auto-logs out sessions that exceed SESSION_COOKIE_AGE
    - Records logout in database when session expires
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        auth = request.session.get("auth")
        
        if auth:
            # Get session timeout from settings (default 8 hours)
            from django.conf import settings
            timeout_seconds = getattr(settings, 'SESSION_COOKIE_AGE', 28800)  # 8 hours default
            
            # Get last activity time
            last_activity_str = request.session.get('last_activity')
            
            if last_activity_str:
                try:
                    last_activity = timezone.datetime.fromisoformat(last_activity_str)
                    if not timezone.is_aware(last_activity):
                        last_activity = timezone.make_aware(last_activity)
                    
                    # Check if session has expired
                    time_since_activity = (timezone.now() - last_activity).total_seconds()
                    
                    if time_since_activity > timeout_seconds:
                        # Session expired - log it out
                        self._auto_logout(request, "Session timeout")
                        request.session.flush()
                        
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid last_activity format: {e}")
            
            # Update last activity time for active sessions
            request.session['last_activity'] = timezone.now().isoformat()
        
        response = self.get_response(request)
        return response
    
    def _auto_logout(self, request, reason="Auto logout"):
        """Record automatic logout in database with actual expiry time"""
        try:
            auth = request.session.get("auth")
            if not auth:
                return
            
            login_log_id = auth.get("login_log_id")
            staff_id = auth.get("staff_id")
            ip = request.META.get("REMOTE_ADDR", "")
            
            # Calculate actual logout time (last_activity + timeout)
            last_activity_str = request.session.get('last_activity')
            if last_activity_str and login_log_id and staff_id:
                from django.conf import settings
                timeout_seconds = getattr(settings, 'SESSION_COOKIE_AGE', 28800)
                
                try:
                    last_activity = timezone.datetime.fromisoformat(last_activity_str)
                    if not timezone.is_aware(last_activity):
                        last_activity = timezone.make_aware(last_activity)
                    
                    # Actual logout time = last activity + timeout
                    actual_logout_time = last_activity + timedelta(seconds=timeout_seconds)
                    
                    # Call logout with backdated time
                    call_staff_logout_with_time(login_log_id, staff_id, ip, actual_logout_time)
                    logger.info(
                        f"AUTO_LOGOUT | staff_id={staff_id} login_log_id={login_log_id} "
                        f"actual_logout={actual_logout_time.isoformat()} reason={reason}"
                    )
                except Exception as e:
                    # Fallback to regular logout if time calculation fails
                    call_staff_logout(login_log_id, staff_id, ip)
                    logger.warning(f"AUTO_LOGOUT fallback | {str(e)}")
        except Exception as e:
            logger.error(f"AUTO_LOGOUT ERROR | {str(e)}", exc_info=True)
