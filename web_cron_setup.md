# Web Cron Setup for Scheduled Announcements

## Option 1: Free Web Cron Services

### 1. cron-job.org (Free)

1. Go to https://cron-job.org
2. Create free account
3. After login, click **"Create cronjob"** button
4. Fill in the form:
   - **Title**: `Process Scheduled Deliveries`
   - **Address (URL)**: `https://your-app-name.onrender.com/process-scheduled-deliveries/`
     (Replace `your-app-name` with your actual Render app name)
   - **Execution**: Select **"Every minute"** from dropdown
   - **Request method**: Select **"POST"** from dropdown
   - **Enabled**: Check the box
5. Click **"Create cronjob"** button
6. Your cron job will now run every minute and call your endpoint

### 2. EasyCron (Free tier)

1. Go to https://www.easycron.com
2. Create account
3. Add cron job with your endpoint URL

### 3. Cronhooks (Free)

1. Go to https://cronhooks.io
2. Create webhook for your endpoint

## Option 2: Add to Django URLs

Add this to your `urls.py`:

```python
from process_scheduled_deliveries_endpoint import process_scheduled_deliveries

urlpatterns = [
    # ... your existing URLs
    path('process-scheduled-deliveries/', process_scheduled_deliveries, name='process_scheduled_deliveries'),
]
```

## Option 3: Django Management Command

Create `management/commands/process_deliveries.py`:

```python
from django.core.management.base import BaseCommand
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.announcement_repository import AnnouncementRepository

class Command(BaseCommand):
    def handle(self, *args, **options):
        ctx = ConnectionAdapter()
        repo = AnnouncementRepository(ctx)

        sql = """
            SELECT DISTINCT ar.announcement_id
            FROM announcement_recipient ar
            JOIN announcement a ON a.announcement_id = ar.announcement_id
            WHERE ar.announcement_deliver_status_id = 1
            AND a.announcement_status_id = 3
        """

        result = ctx.execute_query(sql)
        for row in result:
            repo._process_pending_deliveries(row[0])
```

Then run: `python manage.py process_deliveries`

## Recommended: Use Option 1 + Option 2

1. Add the endpoint to your Django URLs
2. Use a free web cron service to call it every minute
