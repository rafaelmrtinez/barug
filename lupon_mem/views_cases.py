# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid

from typing import Dict, Set
from datetime import date as _date
from django.db import connection

from lupon_mem.services.forms.kp8 import KP8Handler  # reuse its normalization
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler
from django.views.decorators.http import require_POST

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}
LUPON_ROLES_LIST = ["BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"]  # pass to templates

from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET

from lupon_mem.utils.http import json_ok, json_err, flash_success, flash_warning, require_post_view
from lupon_mem.utils.params import post_int, post_bool, post_str
from lupon_mem.utils.logging import blotter_log_event
from lupon_mem.services import hearings as svc_hear
from django.views.decorators.csrf import csrf_protect
import logging
log = logging.getLogger(__name__)

from django.shortcuts import render, redirect
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    HttpResponseNotFound,
)
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connection, transaction
from django.urls import reverse
from django.conf import settings

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

from lupon_mem.services.form_renderer import render_preview_png, render_final_pdf
from django.core.exceptions import ValidationError
from lupon_mem.constants import KP_FORMS_CATALOG   # static chooser catalog

from django.db.models import Prefetch
from django.views.generic import TemplateView, View
from django.shortcuts import get_object_or_404, redirect
from .models import BlotterKpSubmission, KpFormField, KpField, BlotterKpAnswer
# views.py  — replace the whole helper with this
from django.conf import settings

# lupon_mem/views.py  (add these imports near the top)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from lupon_mem.services.case_state import close_case, reopen_case
from lupon_mem.services.helpers import (
    ordinal,
    one_val, row, rows,
    get_form_id, submitted_codes, latest_submission_for_codes,
    latest_notice_submitted_at, is_hearing_held, hearings_held, hearing_gate,
    prefill_minimal_for_case, create_and_submit_form_from_prefill,
    list_case_photos, list_mediation_photos,
    get_person_mobile_number,
    slice_until_code,
)

from django.db import DatabaseError

from lupon_mem.services.all_helpers import *
# --- list cases (with safe search) ---
from urllib.parse import urlencode


# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}




def _hearing_gate(case_id: int) -> dict:
    """Minimal gate helper for case detail."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE s.submitted_at IS NOT NULL) as hearings_set,
                0 as hearings_held,
                MAX(s.submitted_at) as latest_notice_submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ('KP-8', 'KP-12')
        """, [case_id])
        row = cur.fetchone()
        return {
            "hearings_set": row[0] if row else 0,
            "hearings_held": row[1] if row else 0,
            "latest_notice_submitted_at": row[2] if row else None,
        }

def _latest_submission_for_codes(case_id: int, codes: list) -> tuple:
    """Get latest submission for given form codes."""
    with connection.cursor() as cur:
        placeholders = ','.join(['%s'] * len(codes))
        cur.execute(f"""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ({placeholders})
            ORDER BY s.submitted_at DESC NULLS LAST
            LIMIT 1
        """, [case_id] + codes)
        return cur.fetchone()

def _fetch_lookups() -> dict:
    """Fetch lookup data for case creation (CACHED)."""
    cache_key = "case_lookups_v1"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_statuses = cur.fetchall()
    
    result = {
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlement_statuses,
    }
    cache.set(cache_key, result, 600)  # Cache for 10 minutes
    return result

def _fetch_case_states() -> list:
    """Fetch case states from database (CACHED)."""
    cache_key = "case_states_v1"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    with connection.cursor() as cur:
        cur.execute("SELECT case_state_id, case_state_name FROM case_state ORDER BY case_state_name")
        result = cur.fetchall()
    
    cache.set(cache_key, result, 600)  # Cache for 10 minutes
    return result

def _to_none_if_blank(value: str) -> str | None:
    """Convert empty string to None."""
    return value.strip() if value and value.strip() else None


def case_list(request: HttpRequest):
    """
    OPTIMIZED case list for fastest loading.
    Now includes mediation window/conciliation gate from fn_case_hearing_window()
    and exposes them to the template via extra tuple columns (7–13).
    """
    t0 = time.perf_counter()
    
    # Auth & navigation
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    # Params with filters
    q = (request.GET.get("q") or "").strip()
    state = (request.GET.get("state") or "").strip()
    settlement = (request.GET.get("settlement") or "").strip()
    filed_from = (request.GET.get("filed_from") or "").strip()
    filed_to = (request.GET.get("filed_to") or "").strip()
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    per_page = 10  # Fixed for performance
    offset = (page - 1) * per_page

    # Cache choices for 10 minutes
    choices_cache_key = "case_choices_v2"
    choices = cache.get(choices_cache_key)
    if not choices:
        with connection.cursor() as cur:
            cur.execute("SELECT case_state_name FROM case_state ORDER BY case_state_name")
            state_choices = [row[0] for row in cur.fetchall()]
            cur.execute("SELECT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
            settlement_choices = [row[0] for row in cur.fetchall()]
        choices = {"state_choices": state_choices, "settlement_choices": settlement_choices}
        cache.set(choices_cache_key, choices, 600)

    # Build WHERE clause with filters
    where_parts = []
    params = []
    
    if q:
        where_parts.append("(bc.blotter_case_num ILIKE %s OR bc.blotter_case_name ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    
    if state:
        where_parts.append("cs.case_state_name = %s")
        params.append(state)
    
    if settlement:
        where_parts.append("ss.settlement_status_name = %s")
        params.append(settlement)
    
    if filed_from:
        where_parts.append("bc.date_filed >= %s")
        params.append(filed_from)
    
    if filed_to:
        where_parts.append("bc.date_filed <= %s")
        params.append(filed_to)
    
    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    # Fast count with proper JOINs
    with connection.cursor() as cur:
        if where_parts:
            count_sql = f"""
                SELECT COUNT(*) FROM blotter_case bc
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                {where_sql}
            """
        else:
            count_sql = "SELECT COUNT(*) FROM blotter_case bc"
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

    # Fast data query - add LATERAL join to fn_case_hearing_window(bc_id)
    with connection.cursor() as cur:
        data_sql = f"""
            SELECT 
                bc.blotter_case_id,                    -- 0
                bc.blotter_case_num,                   -- 1
                bc.blotter_case_name,                  -- 2
                TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'Mon DD, YYYY') AS processed_on_date,   -- 3
                TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'HH12:MI AM')   AS processed_on_time,   -- 4
                COALESCE(cs.case_state_name, 'PENDING')        AS case_state,         -- 5
                COALESCE(ss.settlement_status_name, 'Pending') AS settlement_status,  -- 6
                COALESCE(ct.complaint_title_name, '')          AS complaint_title,    -- 7
                COALESCE(cn.case_name, '')                     AS case_nature,        -- 8
                TO_CHAR(bc.date_filed, 'Mon DD, YYYY')         AS date_filed,         -- 9
                TO_CHAR(bc.time_filed, 'HH12:MI AM')           AS time_filed,         -- 10

                -- ===== fn_case_hearing_window extras (may be NULL if no KP-8 yet) =====
                hw.window_end_date_text,      -- 11  e.g., "November 12, 2025"
                hw.window_end_time_text,      -- 12  e.g., "10:09 pm"
                hw.days_left,                 -- 13
                hw.can_set_mediation,         -- 14
                hw.can_set_conciliation,      -- 15
                COALESCE(hw.mediation_hearings_set,  0) AS mediation_hearings_set,   -- 16
                COALESCE(hw.mediation_hearings_held, 0) AS mediation_hearings_held   -- 17
            FROM blotter_case bc
            LEFT JOIN case_state       cs ON cs.case_state_id = bc.case_state_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN complaint_title   ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature       cn ON cn.case_nature_id = bc.case_nature_id

            -- Pull the 15-day mediation window + counters for each row
            LEFT JOIN LATERAL fn_case_hearing_window(bc.blotter_case_id) hw ON TRUE

            {where_sql}
            ORDER BY bc.blotter_case_num DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(data_sql, params + [per_page, offset])
        rows = cur.fetchall()

    # Simple pagination
    total_pages = max((total + per_page - 1) // per_page, 1)
    has_prev = page > 1
    has_next = page < total_pages
    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))
    
    # Accurate Statistics using correct case states
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) as total_cases,
                COUNT(*) FILTER (WHERE UPPER(COALESCE(cs.case_state_name, 'PENDING')) = 'OPEN') as open_cases,
                COUNT(*) FILTER (WHERE ss.settlement_status_id IN (2, 15, 16) OR UPPER(COALESCE(ss.settlement_status_name, '')) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION')) as settled_cases
            FROM blotter_case bc
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
        """)
        stats = cur.fetchone()

    total_ms = (time.perf_counter() - t0) * 1000
    log.info(f"case_list optimized: {total_ms:.1f}ms, {total} cases")

    ctx = {
        "page_path": f"{user_role} / Cases",
        "page_title": "Cases",
        "rows": rows,
        "q": q,
        "state": state,
        "settlement": settlement,
        "filed_from": filed_from,
        "filed_to": filed_to,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "prev_page": page - 1,
        "next_page": page + 1,
        "first_item": offset + 1 if total else 0,
        "last_item": min(offset + per_page, total),
        "page_numbers": page_numbers,
        "state_choices": choices["state_choices"],
        "settlement_choices": choices["settlement_choices"],
        "stats": {
            "total_cases": stats[0] if stats else 0,
            "open_cases": stats[1] if stats else 0,
            "settled_cases": stats[2] if stats else 0,
        },
        "load_time_ms": f"{total_ms:.1f}",
    }

    return render(request, "lupon_mem/case_list_offline.html", ctx)

# lupon_mem/views_cases.py (or wherever your case detail view lives)
from lupon_mem.services.hearings_window import get_hearing_window
from lupon_mem.services.fields_util import get_latest_form_fields, get_field_text
from datetime import datetime, timedelta

@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer", "barangay secretary")
def case_detail(request: HttpRequest, case_id: int):
    """OPTIMIZED: Minimal queries, no JSON aggregation"""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                TO_CHAR(bc.date_filed,'Mon DD, YYYY'), bc.incident_desc,
                COALESCE(ct.complaint_title_name,''), COALESCE(cn.case_name,''),
                ss.settlement_status_name, bc.settlement_status_id,
                cs.case_state_name, bc.closed_at,
                (SELECT COUNT(*) FROM blotter_kp_submission WHERE blotter_case_id = %s),
                (SELECT COUNT(*) FROM blotter_kp_submission s JOIN kp_form kf ON kf.form_id = s.form_id 
                 WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-9'),
                (SELECT COUNT(*) FROM blotter_kp_submission s JOIN kp_form kf ON kf.form_id = s.form_id 
                 WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ('KP-8','KP-12') AND s.submitted_at IS NOT NULL)
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id = %s
        """, [case_id, case_id, case_id, case_id])
        case_row = cur.fetchone()
        if not case_row: return HttpResponseNotFound("Case not found")

        cur.execute("""
            SELECT s.submission_id, UPPER(kf.form_code) AS code, kf.form_name, s.status,
                MAX(CASE WHEN a.field_id = 1120 THEN a.value_json #>> '{}' END),
                MAX(CASE WHEN a.field_id = 1121 THEN a.value_json #>> '{}' END),
                MAX(CASE WHEN a.field_id = 1122 THEN a.value_json #>> '{}' END)
            FROM blotter_kp_submission s 
            JOIN kp_form kf ON kf.form_id = s.form_id
            LEFT JOIN blotter_kp_answer a ON a.submission_id = s.submission_id AND a.field_id IN (1120,1121,1122)
            WHERE s.blotter_case_id = %s
            GROUP BY s.submission_id, kf.form_code, kf.form_name, s.status
            ORDER BY s.submission_id DESC
        """, [case_id])
        forms = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in cur.fetchall()]

        cur.execute("""
            SELECT UPPER(kf.form_code) FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id = %s ORDER BY s.submission_id DESC
        """, [case_id])
        all_form_codes = [r[0] for r in cur.fetchall()]
        
        cur.execute("""
            SELECT DISTINCT UPPER(kf.form_code) FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id = %s AND UPPER(s.status) = 'SUBMITTED'
              AND UPPER(kf.form_code) IN ('KP-7','KP-8','KP-9','KP-10','KP-11','KP-12','KP-16')
        """, [case_id])
        submitted_form_codes = {r[0] for r in cur.fetchall()}

    flow_steps = ['KP-7', 'KP-8', 'KP-9', 'KP-10', 'KP-11', 'KP-12', 'KP-16']
    progress_percentage = int((sum(1 for s in flow_steps if s in submitted_form_codes) / len(flow_steps)) * 100)
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    return render(request, "lupon_mem/case_detail.html", {
        "case": case_row, "forms": forms, "case_id": case_id,
        "hearing_window": None, "settlement_choices": ["Settled", "Not Settled", "Pending"],
        "incident_description": case_row[4], "case_nature": case_row[6],
        "case_state_name": case_row[9], "case_closed_at": case_row[10],
        "settlement_statuses": _fetch_lookups()["settlement_statuses"],
        "case_states": _fetch_case_states(),
        "kp9_count": int(case_row[12] or 0), "hearings_set_count": int(case_row[13] or 0),
        "hearings_count": 0, "has_hearing": False,
        "submitted_form_codes": list(submitted_form_codes),
        "progress_percentage": progress_percentage,
        'page_path': f'{user_role} / Case Detail', 'page_title': f'Case #{case_row[1]}',
        "all_form_codes": all_form_codes, "repudiation_window": None,
        "pangkat_members": [], "kp7_details": {}, "upcoming_hearings_count": 0,
    })




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_new(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
        ctx = {
            "lookups": _fetch_lookups(),
            "initial": {},
            'page_path': f'{user_role} / New Case',
            'page_title': 'New Blotter Case',
        }
        return render(request, "lupon_mem/case_new.html", ctx)

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    blotter_case_name = _to_none_if_blank(request.POST.get("blotter_case_name"))
    incident_desc = _to_none_if_blank(request.POST.get("incident_desc"))

    if not blotter_case_name:
        return HttpResponseBadRequest("Case name is required.")

    def _toi(x):
        try:
            return int(x) if x not in (None, "", "0") else None
        except Exception:
            return None

    complaint_title_id = _toi(request.POST.get("complaint_title_id"))
    case_nature_id = _toi(request.POST.get("case_nature_id"))
    settlement_status_id = _toi(request.POST.get("settlement_status_id"))
    blotter_report_id = _toi(request.POST.get("blotter_report_id"))

    date_filed = _to_none_if_blank(request.POST.get("date_filed"))
    time_filed = _to_none_if_blank(request.POST.get("time_filed"))
    incident_date = _to_none_if_blank(request.POST.get("incident_date"))
    incident_time = _to_none_if_blank(request.POST.get("incident_time"))

    incident_location = _to_none_if_blank(request.POST.get("incident_location"))

    complainants = request.POST.getlist("complainants[]")
    respondents = request.POST.getlist("respondents[]")

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO blotter_case
                    (blotter_case_name, date_filed, time_filed,
                     incident_date, incident_time, incident_location, incident_desc,
                     complaint_title_id, case_nature_id, blotter_report_id, settlement_status_id, added_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING blotter_case_id
            """,
                [
                    blotter_case_name,
                    date_filed,
                    time_filed,
                    incident_date,
                    incident_time,
                    incident_location,
                    incident_desc,
                    complaint_title_id,
                    case_nature_id,
                    blotter_report_id,
                    settlement_status_id,
                    staff_id,
                ],
            )
            case_id = cur.fetchone()[0]
            
            # Get staff name and case number for logging
            staff_name = None
            case_num = None
            if staff_id:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                    [staff_id]
                )
                staff_row = cur.fetchone()
                staff_name = staff_row[0] if staff_row else None
            cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id = %s", [case_id])
            case_row = cur.fetchone()
            case_num = case_row[0] if case_row else None
            
            complainants_count = len([p for p in complainants if p and p.isdigit()])
            respondents_count = len([p for p in respondents if p and p.isdigit()])
            message = f"{staff_name or f'Staff ID {staff_id}'} created new case {case_num or f'#{case_id}'} – {blotter_case_name} ({complainants_count} complainant(s), {respondents_count} respondent(s))"
            
            blotter_log_event(
                action="CREATE_CASE",
                table_affected="blotter_case",
                record_affected_id=case_id,
                details=message,
                performer_staff_id=staff_id
            )

            for pid in complainants:
                if pid and pid.isdigit():
                    cur.execute(
                        """
                        INSERT INTO complainant_case (blotter_case_id, person_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                        [case_id, int(pid)],
                    )
            for pid in respondents:
                if pid and pid.isdigit():
                    cur.execute(
                        """
                        INSERT INTO respondent_case (blotter_case_id, person_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                        [case_id, int(pid)],
                    )

    messages.success(request, "Blotter case created.")
    return redirect("lupon_mem:case_detail", case_id=case_id)




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def case_settlement_update(request: HttpRequest, case_id: int):
    """Handle the Update Settlement Status modal submit (with debug prints)."""
    status_name = (request.POST.get("settlement_status") or "").strip()
    remarks     = (request.POST.get("remarks") or "").strip() or None
    staff_id    = (request.session.get("auth") or {}).get("staff_id")

    # --- DEBUG: echo the incoming payload ---
    print("\n[SETTLEMENT][POST] case_id=", case_id)
    print("[SETTLEMENT][POST] payload:", {
        "settlement_status": status_name,
        "remarks": remarks,
        "staff_id": staff_id,
    })
    log.debug("[SETTLEMENT][POST] case_id=%s status=%s remarks=%s staff_id=%s",
              case_id, status_name, remarks, staff_id)

    if not status_name:
        messages.error(request, "Please choose a settlement status.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT ss.settlement_status_name FROM blotter_case bc LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            old_row = cur.fetchone()
            old_settlement = old_row[0] if old_row else None
            
            print("[SETTLEMENT][SQL] calling fn_set_case_settlement(%s,%s,%s,%s)")
            cur.execute(
                "SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                [case_id, status_name, remarks, staff_id],
            )
            row = cur.fetchone()
            print("[SETTLEMENT][SQL][RESULT]:", row)
            log.debug("[SETTLEMENT][SQL][RESULT]: %s", row)

        ok, _case, new_status, changed_at = row if row else (False, None, None, None)
        if ok:
            # Get staff name and case details for logging
            staff_name = None
            case_num = None
            case_name = None
            with connection.cursor() as cur:
                if staff_id:
                    cur.execute(
                        "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                        [staff_id]
                    )
                    staff_row = cur.fetchone()
                    staff_name = staff_row[0] if staff_row else None
                cur.execute("SELECT blotter_case_num, blotter_case_name FROM blotter_case WHERE blotter_case_id = %s", [case_id])
                case_row = cur.fetchone()
                case_num = case_row[0] if case_row else None
                case_name = case_row[1] if case_row else None
            
            message = f"{staff_name or f'Staff ID {staff_id}'} updated settlement status to {new_status} for Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'}"
            if remarks:
                message += f" (remarks: {remarks})"
            
            blotter_log_event(
                action="UPDATE_SETTLEMENT",
                table_affected="blotter_case",
                record_affected_id=case_id,
                details=message,
                performer_staff_id=staff_id,
                field_changed="settlement_status",
                old_value=old_settlement,
                new_value=new_status
            )
            messages.success(request, f'Settlement status updated to "{new_status}".')
        else:
            messages.warning(request, "No change was made.")
    except Exception as e:
        print("[SETTLEMENT][ERROR]:", e)
        log.exception("Settlement update failed")
        messages.error(request, f"Failed to update settlement status: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def case_close(request: HttpRequest, case_id: int):
    """
    POST only. Close a case -> sets state=CLOSED, stamps closed_at/closed_by, logs history.
    """
    note = (request.POST.get("close_note") or "").strip() or None

    # Best-effort staff id discovery. Adjust to your auth model if needed.
    staff_id    = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        messages.error(request, "Cannot determine current staff user.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT cs.case_state_name FROM blotter_case bc LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            old_row = cur.fetchone()
            old_state = old_row[0] if old_row else None
        
        close_case(case_id, staff_id, note)
        
        # Get staff name and case details for logging
        staff_name = None
        case_num = None
        case_name = None
        with connection.cursor() as cur:
            if staff_id:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                    [staff_id]
                )
                staff_row = cur.fetchone()
                staff_name = staff_row[0] if staff_row else None
            cur.execute("SELECT blotter_case_num, blotter_case_name FROM blotter_case WHERE blotter_case_id = %s", [case_id])
            case_row = cur.fetchone()
            case_num = case_row[0] if case_row else None
            case_name = case_row[1] if case_row else None
        
        message = f"{staff_name or f'Staff ID {staff_id}'} closed Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'}"
        if note:
            message += f" (note: {note})"
        
        blotter_log_event(
            action="CLOSE_CASE",
            table_affected="blotter_case",
            record_affected_id=case_id,
            details=message,
            performer_staff_id=staff_id,
            field_changed="case_state",
            old_value=old_state,
            new_value="CLOSED"
        )
        messages.success(request, "Case has been closed.")
    except Exception as e:
        messages.error(request, f"Failed to close case: {e}")
    return redirect("lupon_mem:case_detail", case_id=case_id)



@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def case_reopen(request: HttpRequest, case_id: int):
    """
    POST only. Reopen a case -> sets state=OPEN, clears closed_* fields, logs history.
    """
    reason = (request.POST.get("reopen_reason") or "").strip() or None

    staff_id    = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        messages.error(request, "Cannot determine current staff user.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT cs.case_state_name FROM blotter_case bc LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            old_row = cur.fetchone()
            old_state = old_row[0] if old_row else None
        
        reopen_case(case_id, staff_id, reason)
        
        # Get staff name and case details for logging
        staff_name = None
        case_num = None
        case_name = None
        with connection.cursor() as cur:
            if staff_id:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                    [staff_id]
                )
                staff_row = cur.fetchone()
                staff_name = staff_row[0] if staff_row else None
            cur.execute("SELECT blotter_case_num, blotter_case_name FROM blotter_case WHERE blotter_case_id = %s", [case_id])
            case_row = cur.fetchone()
            case_num = case_row[0] if case_row else None
            case_name = case_row[1] if case_row else None
        
        message = f"{staff_name or f'Staff ID {staff_id}'} reopened Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'}"
        if reason:
            message += f" (reason: {reason})"
        
        blotter_log_event(
            action="REOPEN_CASE",
            table_affected="blotter_case",
            record_affected_id=case_id,
            details=message,
            performer_staff_id=staff_id,
            field_changed="case_state",
            old_value=old_state,
            new_value="OPEN"
        )
        messages.success(request, "Case has been reopened.")
    except Exception as e:
        messages.error(request, f"Failed to reopen case: {e}")
    return redirect("lupon_mem:case_detail", case_id=case_id)



@session_login_required
@role_required(*LUPON_ROLES)
def add_form_choose(request, case_id: int):
    t0 = time.perf_counter()
    cache_key = "kp_forms_active_v1"
    forms = cache.get(cache_key)
    cache_hit = forms is not None
    sql_ms = 0.0
    if not cache_hit:
        with connection.cursor() as cur:
            ts = time.perf_counter()
            cur.execute("""
                SELECT form_id, form_code, form_name
                FROM kp_form
                WHERE is_active IS TRUE
                ORDER BY form_code
            """)
            sql_ms = (time.perf_counter() - ts) * 1000
            forms = cur.fetchall()
        cache.set(cache_key, forms, 300)
    total_ms = (time.perf_counter() - t0) * 1000
    log.info("add_form_choose total=%.1fms sql=%s cache=%s",
             total_ms, f"{sql_ms:.1f}ms" if not cache_hit else "0ms(hit)", cache_hit)
    gate = _hearing_gate(case_id)
    return render(
        request,
        "lupon_mem/add_form_choose.html",
        {"case_id": case_id, "forms": forms, "hearing_gate": gate}
    )

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def mediation_hearings_api(request, case_id: int):
    """API endpoint to get mediation hearing details"""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
            columns = [col[0] for col in cur.description]
            hearings = [dict(zip(columns, row)) for row in cur.fetchall()]
        return JsonResponse(hearings, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
