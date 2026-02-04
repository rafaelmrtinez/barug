# lupon_pres/views_hearing_api.py
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
def hearing_status_api(request: HttpRequest, case_id: int):
    """API endpoint for hearing status"""
    # Implementation mirrors lupon_mem.views_hearing_api.hearing_status_api
    try:
        with connection.cursor() as cur:
            # Get latest hearing information
            cur.execute("""
                WITH latest_hearing AS (
                    SELECT 
                        s.submission_id,
                        f.form_code,
                        s.submitted_at,
                        ROW_NUMBER() OVER (ORDER BY s.submitted_at DESC) as rn
                    FROM blotter_kp_submission s
                    JOIN kp_form f ON f.form_id = s.form_id
                    WHERE s.blotter_case_id = %s
                      AND UPPER(f.form_code) IN ('KP-8', 'KP-12')
                      AND UPPER(s.status) = 'SUBMITTED'
                )
                SELECT 
                    submission_id,
                    form_code,
                    submitted_at
                FROM latest_hearing
                WHERE rn = 1
            """, [case_id])
            
            hearing_data = cur.fetchone()
            
            # Check if hearing was held
            cur.execute("""
                SELECT COUNT(*) > 0 as hearing_held
                FROM case_progress_tracking cpt
                JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                WHERE cpt.blotter_case_id = %s
                  AND UPPER(t.case_progress_type_name) IN ('HEARING HELD', 'CONCILIATION HELD')
            """, [case_id])
            
            hearing_held = cur.fetchone()[0] if cur.rowcount else False
            
        return JsonResponse({
            "case_id": case_id,
            "hearing_held": hearing_held,
            "latest_hearing": {
                "submission_id": hearing_data[0] if hearing_data else None,
                "form_code": hearing_data[1] if hearing_data else None,
                "submitted_at": hearing_data[2].isoformat() if hearing_data and hearing_data[2] else None
            } if hearing_data else None,
            "current_step": "start",  # Default step
            "hearing_no": 1,
            "hearing_attempt": 1
        })
        
    except Exception as e:
        log.exception("Error in hearing_status_api")
        return JsonResponse({"error": "Internal server error"}, status=500)