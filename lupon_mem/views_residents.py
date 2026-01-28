# lupon_mem/views_residents.py
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.contrib import messages
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

LUPON_ROLES = ("BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT")

@session_login_required
@role_required(*LUPON_ROLES)
@nocache
def resident_list(request: HttpRequest) -> HttpResponse:
    """Display resident list with search and filters."""
    q = request.GET.get("q", "").strip()
    purok = request.GET.get("purok", "").strip()
    
    try:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("""
                SELECT p.person_id, p.person_code, p.first_name, p.middle_name, p.last_name, 
                       p.suffix, p.birthdate, p.age, p.mobile_num, p.email, p.person_img
                FROM person p
                WHERE p.person_status_id = 1
                ORDER BY p.last_name, p.first_name
            """)
            rows = [{
                'person_id': r[0], 'person_code': r[1], 'first_name': r[2], 'middle_name': r[3],
                'last_name': r[4], 'suffix': r[5], 'birthdate': r[6], 'age': r[7],
                'mobile_num': r[8], 'email': r[9], 'person_img': r[10], 'address': ''
            } for r in cur.fetchall()]
        
        print(f"Found {len(rows)} residents with person_status_id=1")
        
        if q:
            rows = [r for r in rows if q.lower() in (r.get('first_name') or '').lower() or 
                    q.lower() in (r.get('last_name') or '').lower() or 
                    q.lower() in (r.get('person_code') or '').lower()]
    except Exception as e:
        print(f"Error fetching residents: {e}")
        import traceback
        traceback.print_exc()
        rows = []
    
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or "").strip().title()
    
    return render(request, "lupon_mem/resident_list.html", {
        "page_path": f"{user_role} / Residents",
        "page_title": "Resident List",
        "q": q,
        "purok": purok,
        "puroks_all": ["Kanipaan", "Pampango", "Lutaw-lutaw", "Mauco"],
        "page_obj": page_obj,
    })

@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def resident_delete(request: HttpRequest, person_id: int) -> HttpResponse:
    """Delete a resident from the system."""
    from django.db import connection
    
    try:
        with connection.cursor() as cur:
            cur.execute("DELETE FROM person WHERE person_id = %s", [person_id])
        messages.success(request, "Resident removed successfully.")
    except Exception as e:
        messages.error(request, f"Failed to remove resident: {str(e)}")
    
    return redirect("lupon_mem:resident_list")
