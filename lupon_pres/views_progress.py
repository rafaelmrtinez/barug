# lupon_pres/views_progress.py
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
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def flow_progress_api(request: HttpRequest, case_id: int):
    """API endpoint for case flow progress"""
    # Implementation mirrors lupon_mem.views_progress.flow_progress_api
    try:
        # Get case progress data
        with connection.cursor() as cur:
            cur.execute("""
                SELECT 
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.date_filed,
                    COALESCE(ss.settlement_status_name, 'PENDING') as settlement_status
                FROM blotter_case bc
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            
            case_data = cur.fetchone()
            if not case_data:
                return JsonResponse({"error": "Case not found"}, status=404)
            
            # Get submitted forms
            cur.execute("""
                SELECT 
                    f.form_code,
                    s.status,
                    s.submitted_at
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id = s.form_id
                WHERE s.blotter_case_id = %s
                ORDER BY s.submitted_at DESC
            """, [case_id])
            
            forms = cur.fetchall()
        
        return JsonResponse({
            "case_id": case_data[0],
            "case_num": case_data[1],
            "date_filed": case_data[2].isoformat() if case_data[2] else None,
            "settlement_status": case_data[3],
            "forms": [
                {
                    "form_code": form[0],
                    "status": form[1],
                    "submitted_at": form[2].isoformat() if form[2] else None
                }
                for form in forms
            ]
        })
        
    except Exception as e:
        log.exception("Error in flow_progress_api")
        return JsonResponse({"error": "Internal server error"}, status=500)