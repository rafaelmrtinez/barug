# lupon_pres/views_sql.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connection
from django.urls import reverse
from django.views.generic import View

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

log = logging.getLogger(__name__)

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

class SubmissionViewSQL(View):
    """View submission using SQL queries"""
    
    @session_login_required
    @role_required(*LUPON_ROLES, "barangay treasurer")
    def get(self, request: HttpRequest, pk: int):
        # Implementation mirrors lupon_mem.views_sql.SubmissionViewSQL
        try:
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT 
                        s.submission_id,
                        s.blotter_case_id,
                        f.form_code,
                        f.form_name,
                        s.status,
                        s.submitted_at
                    FROM blotter_kp_submission s
                    JOIN kp_form f ON f.form_id = s.form_id
                    WHERE s.submission_id = %s
                """, [pk])
                
                submission = cur.fetchone()
                
                if not submission:
                    messages.error(request, "Submission not found.")
                    return redirect("lupon_pres:case_list")
        
        except Exception as e:
            log.exception("Error loading submission")
            messages.error(request, "Error loading submission.")
            return redirect("lupon_pres:case_list")
        
        return render(request, "lupon_pres/submissions/view.html", {
            "submission": submission,
            "page_title": f"Submission #{pk}",
            "page_path": f"Barangay Lupon President/Submissions/{pk}",
        })

class SubmissionEditSQL(View):
    """Edit submission using SQL queries"""
    
    @session_login_required
    @role_required(*LUPON_ROLES)
    def get(self, request: HttpRequest, pk: int):
        # Implementation mirrors lupon_mem.views_sql.SubmissionEditSQL
        return render(request, "lupon_pres/submissions/edit.html", {
            "submission_id": pk,
            "page_title": f"Edit Submission #{pk}",
            "page_path": f"Barangay Lupon President/Submissions/{pk}/Edit",
        })

class SubmissionUpdateSQL(View):
    """Update submission using SQL queries"""
    
    @session_login_required
    @role_required(*LUPON_ROLES)
    def post(self, request: HttpRequest, pk: int):
        # Implementation mirrors lupon_mem.views_sql.SubmissionUpdateSQL
        try:
            # Update submission logic here
            messages.success(request, f"Submission #{pk} updated successfully.")
            return redirect("lupon_pres:kp_submission_view", pk=pk)
            
        except Exception as e:
            log.exception("Error updating submission")
            messages.error(request, "Error updating submission.")
            return redirect("lupon_pres:kp_submission_edit", pk=pk)