# lupon_pres/views_resident_records.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_GET
from django.db import connection
from django.urls import reverse
from django.core.paginator import Paginator

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

log = logging.getLogger(__name__)

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@nocache
def resident_records_list(request: HttpRequest):
    """List resident records with search and pagination"""
    # Implementation mirrors lupon_mem.views_resident_records.resident_records_list
    
    search_query = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)
    
    try:
        with connection.cursor() as cur:
            if search_query:
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
                    LIMIT 100
                """, [f'%{search_query}%'])
            else:
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
                    ORDER BY p.last_name, p.first_name
                    LIMIT 50
                """)
            
            residents = cur.fetchall()
    
    except Exception as e:
        log.exception("Error loading resident records")
        residents = []
        messages.error(request, "Error loading resident records.")
    
    # Paginate results
    paginator = Paginator(residents, 20)
    page_obj = paginator.get_page(page_number)
    
    return render(request, "lupon_pres/resident_records_list.html", {
        "page_obj": page_obj,
        "search_query": search_query,
        "page_title": "Resident Records",
        "page_path": "Barangay Lupon President/Resident Records",
    })

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def resident_records_detail(request: HttpRequest, person_id: int):
    """Detailed view of resident record"""
    # Implementation mirrors lupon_mem.views_resident_records.resident_records_detail
    
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT 
                    p.person_id,
                    p.first_name,
                    p.last_name,
                    p.middle_name,
                    p.suffix,
                    p.birthdate,
                    p.mobile_number,
                    p.email,
                    s.sex_name,
                    cs.civil_status_name,
                    a.street,
                    ps.purok_sitio_name,
                    a.barangay,
                    a.city
                FROM person p
                LEFT JOIN sex s ON s.sex_id = p.sex_id
                LEFT JOIN civil_status cs ON cs.civil_status_id = p.civil_status_id
                LEFT JOIN addresss a ON a.address_id = p.address_id
                LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                WHERE p.person_id = %s
            """, [person_id])
            
            resident = cur.fetchone()
            
            if not resident:
                messages.error(request, "Resident not found.")
                return redirect("lupon_pres:resident_records_list")
            
            # Get case involvement
            cur.execute("""
                SELECT 
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.date_filed,
                    'Complainant' as role
                FROM complainant_case cc
                JOIN blotter_case bc ON bc.blotter_case_id = cc.blotter_case_id
                WHERE cc.person_id = %s
                
                UNION ALL
                
                SELECT 
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.date_filed,
                    'Respondent' as role
                FROM respondent_case rc
                JOIN blotter_case bc ON bc.blotter_case_id = rc.blotter_case_id
                WHERE rc.person_id = %s
                
                ORDER BY date_filed DESC
            """, [person_id, person_id])
            
            cases = cur.fetchall()
    
    except Exception as e:
        log.exception("Error loading resident details")
        messages.error(request, "Error loading resident details.")
        return redirect("lupon_pres:resident_records_list")
    
    return render(request, "lupon_pres/resident_records_detail.html", {
        "resident": resident,
        "cases": cases,
        "page_title": f"Resident: {resident[1]} {resident[2]}",
        "page_path": f"Barangay Lupon President/Resident Records/{person_id}",
    })

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def resident_records_api(request: HttpRequest):
    """API endpoint for resident records search"""
    # Implementation mirrors lupon_mem.views_resident_records.resident_records_api
    
    q = request.GET.get('q', '').strip()
    
    try:
        with connection.cursor() as cur:
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
                LIMIT 20
            """, [f'%{q}%'])
            
            results = [
                {
                    "person_id": row[0],
                    "full_name": row[1],
                    "mobile_number": row[2],
                    "street": row[3],
                    "purok_sitio": row[4]
                }
                for row in cur.fetchall()
            ]
        
        return JsonResponse({"results": results})
        
    except Exception as e:
        log.exception("Error in resident_records_api")
        return JsonResponse({"error": "Search failed"}, status=500)