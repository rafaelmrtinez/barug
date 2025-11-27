from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.announcement_repository import AnnouncementRepository

@csrf_exempt
@require_http_methods(["POST"])
def process_scheduled_deliveries(request):
    """Endpoint to process scheduled deliveries - call this from your cron job or manually"""
    try:
        ctx = ConnectionAdapter()
        announcement_repo = AnnouncementRepository(ctx)
        
        # Get recently published announcements that need delivery processing
        sql = """
            SELECT DISTINCT ar.announcement_id
            FROM announcement_recipient ar
            JOIN announcement a ON a.announcement_id = ar.announcement_id
            WHERE ar.announcement_deliver_status_id = 1
            AND a.announcement_status_id = 3
            AND a.announcement_published_at >= now() - interval '5 minutes'
        """
        
        result = ctx.execute_query(sql)
        processed_count = 0
        
        for row in result:
            announcement_id = row[0]
            announcement_repo._process_pending_deliveries(announcement_id)
            processed_count += 1
        
        return JsonResponse({
            'success': True,
            'processed_announcements': processed_count
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)