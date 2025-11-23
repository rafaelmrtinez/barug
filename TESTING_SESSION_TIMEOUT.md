# Testing Session Timeout (3 Minutes)

## Current Test Configuration
- **Session Timeout: 3 minutes** (180 seconds)
- **Setting:** `SESSION_COOKIE_AGE = 60 * 3` in `settings.py`

## How to Test

### Step 1: Restart the Server
```bash
# Stop the server (Ctrl+C)
# Start it again
python manage.py runserver
```

### Step 2: Login
1. Open your browser
2. Go to the login page
3. Login with your credentials
4. Note the time you logged in

### Step 3: Wait 3+ Minutes
1. **DO NOT** click logout
2. **DO NOT** refresh or click anything
3. Just wait for 3 minutes and 10 seconds (to be safe)

### Step 4: Make a Request
After 3+ minutes, do ONE of these:
- Refresh the page (F5)
- Click any link in the navigation
- Try to access any page

### Expected Result
✅ You should be automatically logged out  
✅ Redirected to login page  
✅ Message: "Please sign in to continue."

### Step 5: Check Database
Check your login logs table to verify:
1. The logout was recorded
2. Logout timestamp is approximately 3 minutes after login
3. Session duration is recorded

### Step 6: Check Server Logs
Look for this message in your console:
```
AUTO_LOGOUT | staff_id=X login_log_id=Y reason=Session timeout
```

## Alternative Test: Using Multiple Tabs

### Test Scenario 1: Active in One Tab
1. Login in Tab 1
2. Wait 2 minutes
3. Click something in Tab 1 (resets activity)
4. Wait 2 more minutes
5. Click something in Tab 1
6. **Result:** Should still be logged in (activity was tracked)

### Test Scenario 2: Inactive in All Tabs
1. Login in Tab 1
2. Open Tab 2 with same site
3. Wait 3+ minutes without clicking anything
4. Try to use either tab
5. **Result:** Both tabs should redirect to login

## Test the Cleanup Command

### Create Test Data
1. Login
2. Manually modify session in database to have old `last_activity`
3. Run: `python manage.py cleanup_expired_sessions`
4. Check if session was cleaned up and logout recorded

## Important Notes

⚠️ **Remember to change back to 8 hours for production!**

Change this line in `settings.py`:
```python
# TESTING (3 minutes)
SESSION_COOKIE_AGE = 60 * 3

# PRODUCTION (8 hours)
SESSION_COOKIE_AGE = 60 * 60 * 8
```

## Troubleshooting

### Session doesn't expire after 3 minutes
- Make sure you restarted the server after changing settings
- Check that middleware is in MIDDLEWARE list
- Verify `last_activity` is being set in session

### Logout not recorded in database
- Check server logs for errors
- Verify `login_log_id` is in session
- Check database connection

### Still logged in after 3 minutes
- Make sure you made a request (refresh/click) after 3 minutes
- The middleware only runs when you make a request
- Check browser console for any JavaScript errors

## Quick Test Script

If you want to test faster, temporarily change to 30 seconds:
```python
SESSION_COOKIE_AGE = 30  # 30 seconds for quick testing
```

Then:
1. Login
2. Wait 35 seconds
3. Refresh page
4. Should be logged out

## What to Look For

✅ **Success Indicators:**
- Automatic redirect to login after timeout
- Logout recorded in database with correct timestamp
- Server log shows "AUTO_LOGOUT" message
- Session is cleared from database

❌ **Failure Indicators:**
- Still logged in after 3+ minutes and refresh
- No logout record in database
- No "AUTO_LOGOUT" in server logs
- Session still exists in database
