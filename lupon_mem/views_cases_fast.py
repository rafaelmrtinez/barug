# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid

from typing import Dict
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
    """Fetch lookup data for case creation."""
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_statuses = cur.fetchall()
    return {
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlement_statuses,
    }

def _to_none_if_blank(value: str) -> str | None:
    """Convert empty string to None."""
    return value.strip() if value and value.strip() else None

def case_list(request: HttpRequest):
    """
    OPTIMIZED case list for fastest loading.
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

    # Fast count
    with connection.cursor() as cur:
        count_sql = f"SELECT COUNT(*) FROM blotter_case bc {where_sql}"
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

    # Fast data query - direct table join
    with connection.cursor() as cur:
        data_sql = f"""
            SELECT 
                bc.blotter_case_id,
                bc.blotter_case_num,
                bc.blotter_case_name,
                TO_CHAR(bc.date_filed, 'Mon DD, YYYY') as date_filed_fmt,
                TO_CHAR(bc.time_filed, 'HH12:MI AM') as time_filed_fmt,
                COALESCE(cs.case_state_name, 'PENDING') as case_state,
                COALESCE(ss.settlement_status_name, 'Pending') as settlement_status
            FROM blotter_case bc
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            {where_sql}
            ORDER BY bc.blotter_case_id DESC
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
                COUNT(*) FILTER (WHERE COALESCE(cs.case_state_name, 'PENDING') IN ('PENDING', 'OPEN')) as open_cases,
                COUNT(*) FILTER (WHERE ss.settlement_status_name = 'Settled') as settled_cases
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

    return render(request, "lupon_mem/case_list_fast.html", ctx)




@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    t0 = time.perf_counter()
    
    # Single optimized query for all case data
    with connection.cursor() as cur:
        cur.execute("""
            WITH case_data AS (
                SELECT
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.blotter_case_name,
                    TO_CHAR(bc.date_filed,'Mon DD, YYYY') AS date_filed,
                    bc.incident_desc,
                    COALESCE(ct.complaint_title_name,'—') AS type_name,
                    COALESCE(cn.case_name,'—') AS nature_name,
                    ss.settlement_status_name,
                    bc.settlement_status_id,
                    cs.case_state_name,
                    bc.closed_at
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                WHERE bc.blotter_case_id = %s
            ),
            forms_data AS (
                SELECT
                    s.submission_id,
                    UPPER(kf.form_code) AS form_code,
                    kf.form_name,
                    s.status,
                    CASE WHEN s.submitted_at IS NULL THEN '—'
                         ELSE TO_CHAR(s.submitted_at,'Mon DD, YYYY HH12:MI AM')
                    END AS submitted_fmt,
                    ppt.party_name AS kp17_party,
                    TRIM(COALESCE(p.last_name,'') || ', ' || COALESCE(p.first_name,'') || ' ' || COALESCE(p.middle_name,'')) AS kp17_person,
                    s.submitted_at
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                LEFT JOIN kp17_repudiation m ON m.submission_id = s.submission_id
                LEFT JOIN kp_party_type ppt ON ppt.kp_party_type_id = m.party_type_id
                LEFT JOIN person p ON p.person_id = m.party_person_id
                WHERE s.blotter_case_id = %s
            ),
            kp9_stats AS (
                SELECT
                    COUNT(*) as kp9_count,
                    COUNT(*) FILTER (WHERE a.submission_id IS NULL) as kp9_pending_count,
                    (SELECT a2.status FROM kp9_attendance a2 
                     JOIN blotter_kp_submission s2 ON s2.submission_id = a2.submission_id
                     WHERE s2.blotter_case_id = %s
                     ORDER BY a2.marked_at DESC NULLS LAST LIMIT 1) as latest_status,
                    (SELECT a2.no_show_party FROM kp9_attendance a2 
                     JOIN blotter_kp_submission s2 ON s2.submission_id = a2.submission_id
                     WHERE s2.blotter_case_id = %s
                     ORDER BY a2.marked_at DESC NULLS LAST LIMIT 1) as latest_party
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id AND UPPER(kf.form_code) = 'KP-9'
                LEFT JOIN kp9_attendance a ON a.submission_id = s.submission_id
                WHERE s.blotter_case_id = %s
            ),
            hearing_stats AS (
                SELECT 
                    COUNT(*) FILTER (WHERE s.submitted_at IS NOT NULL) as hearings_set,
                    MAX(s.submitted_at) as latest_notice_submitted_at
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ('KP-8', 'KP-12')
            )
            SELECT 
                cd.*,
                fd.submission_id, fd.form_code, fd.form_name, fd.status, fd.submitted_fmt, 
                fd.kp17_party, fd.kp17_person, fd.submitted_at,
                ks.kp9_count, ks.kp9_pending_count, ks.latest_status, ks.latest_party,
                hs.hearings_set, hs.latest_notice_submitted_at
            FROM case_data cd
            CROSS JOIN kp9_stats ks
            CROSS JOIN hearing_stats hs
            LEFT JOIN forms_data fd ON TRUE
            ORDER BY (fd.submitted_at IS NULL), fd.submitted_at DESC, fd.submission_id DESC
        """, [case_id, case_id, case_id, case_id, case_id, case_id])
        
        rows = cur.fetchall()
        
        if not rows:
            return HttpResponseNotFound("Case not found")
        
        # Extract case data from first row
        first_row = rows[0]
        case = first_row[:11]  # First 11 columns are case data
        case_state_name = first_row[9]
        case_closed_at = first_row[10]
        
        # Extract stats
        kp9_count = first_row[18] or 0
        kp9_pending_count = first_row[19] or 0
        kp9_latest_status = (first_row[20] or "").upper() if first_row[20] else None
        kp9_latest_party = (first_row[21] or "").upper() if first_row[21] else None
        hearings_set_count = first_row[22] or 0
        latest_notice_dt = first_row[23]
        
        # Extract forms data
        forms_raw = []
        for row in rows:
            if row[11]:  # submission_id exists
                forms_raw.append(row[11:18])  # Form columns
        
        # Cache settlement choices
        cache_key = "settlement_choices_v1"
        settlement_choices = cache.get(cache_key)
        if not settlement_choices:
            cur.execute("SELECT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
            settlement_choices = [r[0] for r in cur.fetchall()]
            cache.set(cache_key, settlement_choices, 600)
    
    # Minimal sequence labeling (only if forms exist)
    forms = forms_raw
    if forms_raw:
        def _ordinal(n: int) -> str:
            n = int(n)
            if 11 <= (n % 100) <= 13:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{suffix}"
        
        # Simple sequence labels
        form_seq_labels = {}
        counters = {"KP-9": 0, "MED-ATT-2025": 0, "KP-8": 0, "KP-12": 0}
        
        for form_data in sorted(forms_raw, key=lambda x: x[7] or '1900-01-01'):  # Sort by submitted_at
            sid, code = int(form_data[0]), form_data[1]
            if code in counters:
                counters[code] += 1
                n = counters[code]
                if code == "KP-9":
                    form_seq_labels[sid] = f"{_ordinal(n)} Summons"
                elif code == "MED-ATT-2025":
                    form_seq_labels[sid] = f"{_ordinal(n)} Med Attendance"
                elif code in ("KP-8", "KP-12"):
                    form_seq_labels[sid] = f"{_ordinal(n)} Hearing"
        
        forms = [(*row, form_seq_labels.get(int(row[0]))) for row in forms_raw]
    
    # Minimal gate logic
    def _fmt_dt(dt) -> str | None:
        if not dt:
            return None
        try:
            from django.utils import timezone
            return timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            return None
    
    latest_hearing_dt = _fmt_dt(latest_notice_dt)
    
    # Simple blocking logic
    block_due_to_summons = kp9_pending_count > 0
    block_reason_summons = f"{kp9_pending_count} summons pending attendance marking." if block_due_to_summons else ""
    
    # Check for MED summary
    has_med_summary = any(f[1] in ["MED1-SETTLED", "MED2-SETTLED", "MED3-SETTLED"] for f in forms_raw)
    med_summary_sid = next((int(f[0]) for f in forms_raw if f[1] in ["MED1-SETTLED", "MED2-SETTLED", "MED3-SETTLED"]), None)
    
    total_ms = (time.perf_counter() - t0) * 1000
    log.info(f"case_detail optimized: {total_ms:.1f}ms")
    
    context = {
        "case": case,
        "forms": forms,
        "case_id": case_id,
        "settlement_choices": settlement_choices,
        "hearing_gate": {"hearings_set": hearings_set_count, "latest_notice_submitted_at": latest_notice_dt},
        
        "incident_description": case[4] if case else None,
        "case_nature": case[6] if case else None,
        "case_state_name": case_state_name,
        "case_closed_at": case_closed_at,
        
        # KPIs
        "latest_hearing_dt": latest_hearing_dt,
        "last_hearing_dt": latest_hearing_dt,
        "kp9_count": kp9_count,
        "hearings_set_count": hearings_set_count,
        "hearings_count": 0,  # Simplified
        
        # KP-9 state
        "kp9_latest_status": kp9_latest_status,
        "kp9_latest_party": kp9_latest_party,
        "kp9_pending_count": kp9_pending_count,
        "has_hearing": hearings_set_count > 0,
        
        # Blocking
        "force_open_block_modal": bool(request.GET.get("open_block_modal")),
        "block_reason": request.GET.get("reason"),
        "block_due_to_summons": block_due_to_summons,
        "block_due_to_hearing": False,  # Simplified
        "block_reason_summons": block_reason_summons,
        "block_reason_hearing": "",
        
        # Summary
        "has_med_summary": has_med_summary,
        "med_summary_sid": med_summary_sid,
        "load_time_ms": f"{total_ms:.1f}",
    }
    
    return render(request, "lupon_mem/case_detail.html", context)




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_new(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        ctx = {
            "lookups": _fetch_lookups(),
            "initial": {},
            "page_title": "New Blotter Case",
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
            messages.success(request, f"Settlement status updated to "{new_status}".")
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
        close_case(case_id, staff_id, note)
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
        reopen_case(case_id, staff_id, reason)
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

