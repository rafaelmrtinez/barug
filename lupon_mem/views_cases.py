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




@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_list(request: HttpRequest):
    """
    Live-searchable case list using v_blotter_case_summary.
    GET:
      q, state, settlement, filed_from (YYYY-MM-DD), filed_to (YYYY-MM-DD),
      page, per_page, partial=1
    """
    from urllib.parse import urlencode
    from django.db import connection

    q          = (request.GET.get("q") or "").strip()
    state      = (request.GET.get("state") or "").strip()        # case_final_status text
    settlement = (request.GET.get("settlement") or "").strip()   # settlement_status text
    filed_from = (request.GET.get("filed_from") or "").strip()
    filed_to   = (request.GET.get("filed_to") or "").strip()

    # pagination
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    try:
        per_page = max(int(request.GET.get("per_page", "10")), 1)
    except ValueError:
        per_page = 10
    offset = (page - 1) * per_page

    # choices (distinct values from the view)
    with connection.cursor() as cur:
        cur.execute("SELECT DISTINCT case_final_status FROM v_blotter_case_summary ORDER BY 1")
        state_choices = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT settlement_status FROM v_blotter_case_summary ORDER BY 1")
        settlement_choices = [row[0] for row in cur.fetchall()]

    base_from = "FROM v_blotter_case_summary v"
    where_parts = []
    params: list = []

    if q:
        where_parts.append("""
            (
              v.blotter_case_num  ILIKE CONCAT('%%', %s, '%%')
           OR v.blotter_case_name ILIKE CONCAT('%%', %s, '%%')
            )
        """)
        params.extend([q, q])

    if state:
        where_parts.append("v.case_final_status = %s")
        params.append(state)

    if settlement:
        where_parts.append("v.settlement_status = %s")
        params.append(settlement)

    if filed_from:
        where_parts.append("v.date_filed >= %s")
        params.append(filed_from)

    if filed_to:
        where_parts.append("v.date_filed <= %s")
        params.append(filed_to)

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # total
    with connection.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) {base_from} {where_sql}", params)
        total = int(cur.fetchone()[0])

    # page rows (adds time_filed)
    with connection.cursor() as cur:
        select_sql = f"""
            SELECT
              v.blotter_case_id,                                       -- 0
              v.blotter_case_num,                                      -- 1
              v.blotter_case_name,                                     -- 2
              to_char(v.date_filed, 'Mon DD, YYYY') AS date_filed_fmt, -- 3
              to_char(v.time_filed, 'HH12:MI AM')    AS time_filed_fmt,-- 4  ← NEW
              v.case_final_status,                                     -- 5
              v.settlement_status                                      -- 6
            {base_from}
            {where_sql}
            ORDER BY v.blotter_case_id DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(select_sql, params + [per_page, offset])
        rows = cur.fetchall()

    # pagination helpers
    total_pages = max((total + per_page - 1) // per_page, 1)
    has_prev = page > 1
    has_next = page < total_pages
    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))

    preserved = {
        "q": q,
        "state": state,
        "settlement": settlement,
        "filed_from": filed_from,
        "filed_to": filed_to,
        "per_page": per_page,
    }
    preserved = {k: v for k, v in preserved.items() if v not in (None, "", [])}
    query_no_page = urlencode(preserved)

    ctx = {
        "rows": rows,
        "q": q,
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
        "query_no_page": query_no_page,

        # filters + choices
        "state": state,
        "settlement": settlement,
        "filed_from": filed_from,
        "filed_to": filed_to,
        "state_choices": state_choices,
        "settlement_choices": settlement_choices,
    }

    if request.GET.get("partial") == "1":
        return render(request, "lupon_mem/partials/case_table.html", ctx)

    return render(request, "lupon_mem/case_list.html", ctx)




@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    from django.utils import timezone
    from django.db import connection

    def _fmt_dt(dt) -> str | None:
        if not dt:
            return None
        try:
            return timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            try:
                return dt.strftime("%b %d, %Y %I:%M %p")
            except Exception:
                return None

    def _ordinal(n: int) -> str:
        n = int(n)
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    with connection.cursor() as cur:
        # ----- Case header
        cur.execute(
            """
            SELECT
              bc.blotter_case_id,
              bc.blotter_case_num,
              bc.blotter_case_name,
              to_char(bc.date_filed,'Mon DD, YYYY') AS date_filed,
              bc.incident_desc,
              COALESCE(ct.complaint_title_name,'—') AS type_name,
              COALESCE(cn.case_name,'—') AS nature_name,
              ss.settlement_status_name,
              bc.settlement_status_id
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn ON cn.case_nature_id   = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id=%s
            """,
            [case_id],
        )
        case = cur.fetchone()

        # ----- Attached forms (list + KP-17 meta)
        cur.execute(
            """
            SELECT
              s.submission_id,
              UPPER(kf.form_code) AS form_code,
              kf.form_name,
              s.status,
              CASE WHEN s.submitted_at IS NULL THEN '—'
                   ELSE to_char(s.submitted_at,'Mon DD, YYYY HH12:MI AM')
              END AS submitted_fmt,
              ppt.party_name AS kp17_party,
              TRIM(
                COALESCE(p.last_name,'') || ', ' ||
                COALESCE(p.first_name,'') || ' ' ||
                COALESCE(p.middle_name,'')
              ) AS kp17_person
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            LEFT JOIN kp17_repudiation m   ON m.submission_id = s.submission_id
            LEFT JOIN kp_party_type  ppt   ON ppt.kp_party_type_id = m.party_type_id
            LEFT JOIN person         p     ON p.person_id = m.party_person_id
            WHERE s.blotter_case_id=%s
            ORDER BY (s.submitted_at IS NULL), s.submitted_at DESC, s.submission_id DESC
            """,
            [case_id],
        )
        forms_raw = cur.fetchall()

        # ----- KP-9 meta (count + latest attendance status/party)
        cur.execute(
            """
            WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
            SELECT COUNT(*) FROM blotter_kp_submission
            WHERE blotter_case_id=%s AND form_id=(SELECT form_id FROM f)
            """,
            [case_id],
        )
        kp9_count = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
            SELECT a.status, a.no_show_party
            FROM kp9_attendance a
            JOIN blotter_kp_submission s ON s.submission_id = a.submission_id
            WHERE s.blotter_case_id = %s
              AND s.form_id = (SELECT form_id FROM f)
            ORDER BY a.marked_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 1
            """,
            [case_id],
        )
        r = cur.fetchone()
        kp9_latest_status = (r[0] or "").upper() if r else None
        kp9_latest_party = (r[1] or "").upper() if r and r[1] else None

        # ----- NEW: count of KP-9 submissions WITHOUT attendance
        cur.execute(
            """
            WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
            SELECT COUNT(*)
            FROM blotter_kp_submission s
            WHERE s.blotter_case_id=%s
              AND s.form_id=(SELECT form_id FROM f)
              AND NOT EXISTS (
                    SELECT 1 FROM kp9_attendance a
                    WHERE a.submission_id = s.submission_id
              )
            """,
            [case_id],
        )
        kp9_pending_count = int((cur.fetchone() or [0])[0] or 0)

        # ----- Settlement choices
        cur.execute("SELECT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_choices = [row[0] for row in cur.fetchall()]

    # ===============================
    # Sequence labels (badges) setup
    # ===============================
    form_seq_labels: dict[int, str] = {}

    # A) Use fn_case_mediation_hearings for KP-8/KP-12 numbering (1st/2nd/3rd Hearing)
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT notice_sid, hearing_no, source
            FROM fn_case_mediation_hearings(%s)
            ORDER BY hearing_no
            """,
            [case_id],
        )
        tvf_rows = cur.fetchall()  # (notice_sid, hearing_no, source)

    for notice_sid, hearing_no, _source in tvf_rows:
        form_seq_labels[int(notice_sid)] = f"{_ordinal(int(hearing_no))} Hearing"

    # B) Also number KP-9 and MED-ATT-2025 (1st Summons / 1st Med Attendance ...)
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.submission_id, UPPER(kf.form_code) AS code, s.submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(kf.form_code) IN ('KP-9','MED-ATT-2025')
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
            """,
            [case_id],
        )
        seq_rows = cur.fetchall()

    counters = {"KP-9": 0, "MED-ATT-2025": 0}
    for sid, code, _submitted_at in seq_rows:
        code = (code or "").upper()
        if code in counters:
            counters[code] += 1
            n = counters[code]
            if code == "KP-9":
                form_seq_labels[int(sid)] = f"{_ordinal(n)} Summons"
            elif code == "MED-ATT-2025":
                form_seq_labels[int(sid)] = f"{_ordinal(n)} Med Attendance"

    # ----- annotate forms: append seq label as last column (index 7)
    forms = [(*row, form_seq_labels.get(int(row[0]))) for row in forms_raw]

    # ===============================
    # Gate logic + KPI values
    # ===============================
    gate = _hearing_gate(case_id)  # expects updated helper that returns 'hearings_set'
    latest_notice_dt = gate.get("latest_notice_submitted_at")
    latest_hearing_dt = _fmt_dt(latest_notice_dt)

    hearings_set_count  = int(gate.get("hearings_set") or 0)
    hearings_held_count = int(gate.get("hearings_held") or 0)

    # ----- NEW blocking logic for Add Form (summons)
    finalized_attendance = {"ATTENDED", "NO SHOW"}
    block_due_to_summons = kp9_pending_count > 0
    if block_due_to_summons:
        if kp9_count and (kp9_latest_status not in finalized_attendance):
            pass  # keep behavior as-is

    block_reason_summons = (
        f"{kp9_pending_count} summons pending attendance marking (ATTENDED / NO SHOW)."
        if block_due_to_summons else ""
    )

    has_upcoming = bool(
        gate.get("has_upcoming_hearing")
        or gate.get("latest_notice_outstanding")
    )
    needs_outcome = bool(
        gate.get("pending_hearing_requires_outcome")
        or gate.get("has_unresolved_mediation")
    )
    block_due_to_hearing = bool(has_upcoming or needs_outcome)
    block_reason_hearing = ""
    if block_due_to_hearing:
        if needs_outcome:
            block_reason_hearing = "There is a mediation/conciliation hearing without a recorded outcome (Settled / Not Settled)."
        elif has_upcoming:
            block_reason_hearing = "There is a scheduled hearing that must be completed or marked with an outcome first."

    force_open_block_modal = bool(request.GET.get("open_block_modal"))
    block_reason = request.GET.get("reason")  # 'summons' | 'hearing' | None
    med_row = _latest_submission_for_codes(case_id, ["MED1-SETTLED","MED2-SETTLED","MED3-SETTLED"])
    has_med_summary = bool(med_row)
    med_summary_sid = int(med_row[0]) if med_row else None

    # Pull case state name + closed_at to drive Close/Reopen UI
    with connection.cursor() as cur:
        cur.execute("""
            SELECT cs.case_state_name, bc.closed_at
            FROM blotter_case bc
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        r = cur.fetchone() or (None, None)
        case_state_name, case_closed_at = r[0], r[1]

    context = {
        "case": case,
        "forms": forms,
        "case_id": case_id,
        "settlement_choices": settlement_choices,
        "hearing_gate": gate,

        "incident_description": case[4] if case else None,
        "case_nature": case[6] if case else None,
        "case_state_name": case_state_name,
        "case_closed_at": case_closed_at,

        # KPIs
        "latest_hearing_dt": latest_hearing_dt,
        "last_hearing_dt": latest_hearing_dt,
        "next_hearing_dt": None,
        "kp9_count": kp9_count,
        "hearings_set_count": hearings_set_count,
        "hearings_count": hearings_held_count,  # kept for “Held” KPI if you still show it

        # KP-9 quick state
        "kp9_latest_status": kp9_latest_status,
        "kp9_latest_party": kp9_latest_party,
        "kp9_pending_count": kp9_pending_count,
        "has_hearing": hearings_held_count > 0,

        # gating / modals
        "force_open_block_modal": force_open_block_modal,
        "block_reason": block_reason,
        "block_due_to_summons": block_due_to_summons,
        "block_due_to_hearing": block_due_to_hearing,
        "block_reason_summons": block_reason_summons,
        "block_reason_hearing": block_reason_hearing,

        # summary availability
        "has_med_summary": has_med_summary,
        "med_summary_sid": med_summary_sid,
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
            messages.success(request, f"Settlement status updated to “{new_status}”.")
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


