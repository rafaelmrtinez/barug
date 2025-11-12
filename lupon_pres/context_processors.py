# lupon_pres/context_processors.py
"""
Context processors for lupon_pres
"""

def lupon_pres_badge_counts(request):
    """Badge counts for lupon_pres navigation"""
    return {
        'lupon_pres_pending_cases': 0,
        'lupon_pres_pending_hearings': 0,
        'lupon_pres_pending_reports': 0,
    }