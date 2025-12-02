"""
Views for in-app announcements
"""
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.db import connection
from .guards import session_login_required

logger = logging.getLogger(__name__)


@session_login_required
def in_app_announcements(request):
    """Display in-app announcements for the current user"""
    person_id = request.session.get('person_id')
    
    if not person_id:
        logger.warning("No person_id in session for in_app_announcements")
        return render(request, 'announcement/in_app_announcement.html', {
            'announcements': [],
            'page_title': 'Announcements',
            'page_path': 'Announcements'
        })
    
    try:
        announcements = get_user_announcements(person_id)
        
        return render(request, 'announcement/in_app_announcement.html', {
            'announcements': announcements,
            'page_title': 'Announcements',
            'page_path': 'Announcements'
        })
    except Exception as e:
        logger.exception(f"Error loading announcements for person {person_id}: {e}")
        return render(request, 'announcement/in_app_announcement.html', {
            'announcements': [],
            'page_title': 'Announcements',
            'page_path': 'Announcements',
            'error': 'Failed to load announcements'
        })


def get_user_announcements(person_id: int) -> list:
    """
    Fetch published announcements that:
    1. Are in PUBLISHED status
    2. Current date/time is between published_at and expire_at (or expire_at is null)
    3. User is in the audience for the announcement
    """
    sql = """
        SELECT DISTINCT
            a.announcement_id,
            a.announcement_title,
            a.announcement_body,
            a.announcement_published_at,
            a.announcement_expire_at,
            a.announcement_created_at
        FROM public.announcement a
        JOIN public.announcement_status ast 
            ON ast.announcement_status_id = a.announcement_status_id
        JOIN public.audience aud 
            ON aud.announcement_id = a.announcement_id
        JOIN public.audience_person_list apl 
            ON apl.audience_id = aud.audience_id
        WHERE apl.person_id = %s
          AND ast.announcement_status_name = 'PUBLISHED'
          AND a.announcement_published_at IS NOT NULL
          AND a.announcement_published_at <= NOW()
          AND (a.announcement_expire_at IS NULL OR a.announcement_expire_at > NOW())
        ORDER BY a.announcement_published_at DESC
        LIMIT 50
    """
    
    with connection.cursor() as cursor:
        cursor.execute(sql, [person_id])
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return results
