# Local Testing for Scheduled Announcements

## Step 1: Test the Complete Flow

1. **Schedule an announcement** (set publish time to 1-2 minutes from now)
2. **Wait for the scheduled time**
3. **Run the test script**:
   ```bash
   python test_scheduled_deliveries.py
   ```

## Step 2: Manual Database Testing

### Check scheduled announcements:
```sql
SELECT announcement_id, announcement_title, announcement_status_id, announcement_published_at 
FROM announcement 
WHERE announcement_status_id = 2;
```

### Manually publish scheduled announcements:
```sql
SELECT * FROM publish_scheduled_announcements();
```

### Check pending recipients:
```sql
SELECT ar.announcement_id, ar.announcement_deliver_status_id, COUNT(*)
FROM announcement_recipient ar
GROUP BY ar.announcement_id, ar.announcement_deliver_status_id;
```

### Test the endpoint manually:
```bash
curl -X POST http://localhost:8000/process-scheduled-deliveries/
```

## Step 3: Add Endpoint to URLs

Add to your main `urls.py`:
```python
from process_scheduled_deliveries_endpoint import process_scheduled_deliveries

urlpatterns = [
    # ... your existing URLs
    path('process-scheduled-deliveries/', process_scheduled_deliveries, name='process_scheduled_deliveries'),
]
```

## Expected Results

- **Email debug logs** should appear when deliveries are processed
- **Delivery status** should change from PENDING (1) to SENT EMAIL (3)
- **delivered_at** timestamp should be set