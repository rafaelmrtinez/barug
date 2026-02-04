# lupon_pres/views_mobile.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_GET
from django.db import connection
from django.urls import reverse

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

log = logging.getLogger(__name__)

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def residents_search(request: HttpRequest):
    """Mobile-optimized residents search"""
    # Implementation mirrors lupon_mem.views_mobile.residents_search
    
    q = request.GET.get('q', '').strip()
    
    try:
        with connection.cursor() as cur:
            if q:
                cur.execute("""
                    SELECT 
                        p.person_id,
                        TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) as full_name,
                        p.mobile_number,
                        a.street,
                        ps.purok_sitio_name
                    FROM person p
                    LEFT JOIN addresss a ON a.address_id = p.address_id
                    LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                    WHERE UPPER(TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, ''))) 
                          LIKE UPPER(%s)
                    ORDER BY p.last_name, p.first_name
                    LIMIT 10
                """, [f'%{q}%'])
                
                results = [
                    {
                        "id": row[0],
                        "name": row[1],
                        "mobile": row[2],
                        "address": f"{row[3] or ''}, {row[4] or ''}".strip(', ')
                    }
                    for row in cur.fetchall()
                ]
            else:
                results = []
        
        return JsonResponse({
            "results": results,
            "query": q
        })
        
    except Exception as e:
        log.exception("Error in mobile residents search")
        return JsonResponse({"error": "Search failed"}, status=500)