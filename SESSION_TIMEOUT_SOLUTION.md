# Session Timeout & Auto-Logout Solution

## Problem
Users who don't explicitly click "logout" are not recorded in the database. This happens when:
- Users close their browser
- Session expires due to inactivity
- Browser crashes
- Network disconnection

## Current Session Settings
- **Session Timeout: 8 hours** (`SESSION_COOKIE_AGE = 60 * 60 * 8`)
- **Location:** `barug/settings.py` line 337
- Sessions expire after 8 hours of inactivity
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = False` - sessions persist even if browser closes

## Solution Implemented

### 1. Session Timeout Middleware
**File:** `authentication/session_timeout_middleware.py`

This middleware:
- Tracks user activity on every request
- Stores `last_activity` timestamp in session
- Automatically detects expired sessions (> 8 hours of inactivity)
- Calls `call_staff_logout()` to record logout in database
- Flushes the expired session

**How it works:**
```python
# On each request:
1. Check if user is authenticated
2. Get last_activity timestamp from session
3. Calculate time since last activity
4. If > 8 hours (SESSION_COOKIE_AGE):
   - Call database logout function
   - Flush session
5. Update last_activity to current time
```

### 2. Updated Login Flow
**File:** `authentication/views.py`

Added initialization of `last_activity` timestamp when user logs in:
```python
request.session['last_activity'] = timezone.now().isoformat()
```

### 3. Cleanup Management Command
**File:** `authentication/management/commands/cleanup_expired_sessions.py`

Run this command to clean up any orphaned sessions:
```bash
python manage.py cleanup_expired_sessions
```

This is useful for:
- Cleaning up sessions that expired before the middleware was added
- Periodic maintenance (can be scheduled with cron/task scheduler)
- Ensuring database consistency

## How to Use

### Automatic (Recommended)
The middleware runs automatically on every request. No action needed.

### Manual Cleanup
Run the cleanup command periodically:
```bash
# Windows
python manage.py cleanup_expired_sessions

# Linux/Mac
python3 manage.py cleanup_expired_sessions
```

### Schedule Periodic Cleanup (Optional)
You can schedule this command to run daily:

**Windows Task Scheduler:**
```
Action: Start a program
Program: python
Arguments: manage.py cleanup_expired_sessions
Start in: d:\CAPSTONE 2\cloned_repo\barug
```

**Linux Cron:**
```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/barug && python3 manage.py cleanup_expired_sessions
```

## Testing

### Test Session Timeout
1. Login to the system
2. Wait 8 hours (or temporarily change `SESSION_COOKIE_AGE` to 60 seconds for testing)
3. Make any request (refresh page, click link)
4. Session should be automatically logged out
5. Check database - logout should be recorded

### Test Manual Cleanup
1. Create some test sessions
2. Manually update `last_activity` in session to be > 8 hours old
3. Run: `python manage.py cleanup_expired_sessions`
4. Verify sessions are cleaned up and logged out in database

## Database Impact

The solution uses the existing `call_staff_logout()` function which calls:
```sql
SELECT * FROM staff_logout2(login_log_id, staff_id, ip_address);
```

This ensures:
- Logout time is recorded
- Session duration is calculated
- Audit trail is maintained
- No additional database changes needed

## Configuration

To change session timeout, edit `barug/settings.py`:
```python
# Current: 8 hours
SESSION_COOKIE_AGE = 60 * 60 * 8

# Examples:
SESSION_COOKIE_AGE = 60 * 60 * 4   # 4 hours
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 hours
SESSION_COOKIE_AGE = 60 * 30       # 30 minutes (for testing)
```

## Monitoring

Check logs for auto-logout events:
```
AUTO_LOGOUT | staff_id=123 login_log_id=456 reason=Session timeout
```

## Benefits

1. **Complete Audit Trail** - All sessions are now logged out, even if user doesn't click logout
2. **Security** - Expired sessions are automatically cleaned up
3. **Accurate Metrics** - Session duration tracking is now accurate
4. **No User Impact** - Works transparently in the background
5. **Database Consistency** - All login records have corresponding logout records

## Notes

- The middleware runs on EVERY request, but the overhead is minimal (just timestamp comparison)
- Sessions are only logged out once (when first detected as expired)
- The solution is backward compatible - existing code continues to work
- Manual logout (clicking logout button) still works as before
