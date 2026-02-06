# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid
import pytz
from zoneinfo import ZoneInfo

from lupon_mem.services.forms.kp8 import KP8Handler  # reuse its normalization
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler
from django.views.decorators.http import require_POST

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}
LUPON_ROLES_LIST = ["BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"]  # pass to templates

from django.views.decorators.http import require_POST


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
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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



# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}


# helpers
def _toi(x):
    try:
        return int(x) if x not in (None, "", "0") else None
    except Exception:
        return None


def _fetch_lookups() -> Dict[str, List[Tuple[int, str]]]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name"
        )
        complaint_titles = cur.fetchall()

        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()

        cur.execute(
            "SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name"
        )
        settlement_statuses = cur.fetchall()

        cur.execute(
            """
            SELECT b.blotter_report_id, COALESCE(b.incident_subject,'(no subject)') || ' — ' || to_char(b.date_time_reported, 'YYYY-MM-DD HH24:MI')
            FROM blotter_report b
            ORDER BY b.date_time_reported DESC
            LIMIT 200
        """
        )
        reports = cur.fetchall()

    return {
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlement_statuses,
        "reports": reports,
    }


def _to_none_if_blank(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()
    return s if s else None



# code
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
def report_list(request: HttpRequest):
    start_time = time.time()
    q_raw = (request.GET.get("q") or "").strip()
    f_payment = (request.GET.get("payment") or "").strip()
    f_blotter = (request.GET.get("blotter_status") or "").strip()
    f_date_from = (request.GET.get("date_from") or "").strip()
    f_date_to = (request.GET.get("date_to") or "").strip()
    f_sort = (request.GET.get("sort") or "newest").strip()

    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()

    payment_options = ["", "PAID", "UNPAID", "DECLINED"]
    blotter_options = ["", "FOR LUPON REVIEW", "REVIEWED"]

    # Get Philippine timezone
    ph_tz = pytz.timezone('Asia/Manila')
    
    with connection.cursor() as cur:
        # Query raw timestamps and convert to Philippine Time
        cur.execute("SELECT blotter_report_id, date_time_reported, incident_subject, payment_status_id FROM blotter_report ORDER BY blotter_report_id DESC")
        raw_reports = cur.fetchall()
        
        cur.execute("SELECT * FROM get_all_report_details() ORDER BY blotter_report_id DESC")
        columns = [col[0] for col in cur.description]
        all_reports = cur.fetchall()
        
        # Create a map of report_id to Philippine Time formatted string
        ph_time_map = {}
        for row in raw_reports:
            report_id, dt_utc = row[0], row[1]
            if dt_utc:
                # Convert UTC to Philippine Time
                dt_ph = dt_utc.astimezone(ph_tz)
                ph_time_map[report_id] = dt_ph.strftime('%B %d, %Y %I:%M %p')
        
        # Convert to tuples for template compatibility
        reports_data = []
        for row in all_reports:
            row_dict = dict(zip(columns, row))
            payment_status = row_dict.get('payment_status_name') or ''
            blotter_status = 'REVIEWED' if payment_status and str(payment_status).upper() in ('PAID','UNPAID','DECLINED') else 'FOR LUPON REVIEW'
            
            # Use Philippine Time from our map
            report_id = row_dict.get('blotter_report_id')
            reported_at = ph_time_map.get(report_id, row_dict.get('date_time_reported'))
            
            # Create tuple: (id, subject, reported_at, payment_status, blotter_status, complainant_names, respondent_names, current_status_name, has_case)
            report_tuple = (
                row_dict.get('blotter_report_id'),
                row_dict.get('incident_subject') or '(no subject)',
                reported_at,
                payment_status,
                blotter_status,
                row_dict.get('complainant_names') or '',
                row_dict.get('respondent_names') or '',
                row_dict.get('current_status_name') or '',
                row_dict.get('has_case') or False
            )
            reports_data.append(report_tuple)
        
        # Apply filters
        filtered_reports = reports_data
        
        # For barangay treasurer, show reports with "FOR CASE FILING" or "ESCALATED TO CASE" status
        if user_role.lower() == 'barangay treasurer':
            filtered_reports = [r for r in filtered_reports if str(r[7]).upper() in ('FOR CASE FILING', 'ESCALATED TO CASE')]
        
        if q_raw:
            filtered_reports = [r for r in filtered_reports if q_raw.lower() in (r[1] or '').lower()]
        
        if f_payment and f_payment.upper() in ("PAID", "UNPAID", "DECLINED"):
            filtered_reports = [r for r in filtered_reports if str(r[3]).upper() == f_payment.upper()]
        
        if f_blotter:
            if f_blotter == 'FOR LUPON REVIEW':
                filtered_reports = [r for r in filtered_reports if r[4] == 'FOR LUPON REVIEW']
            elif f_blotter == 'REVIEWED':
                filtered_reports = [r for r in filtered_reports if r[4] == 'REVIEWED']
        
        # Apply sorting (default is newest first - DESC order)
        if f_sort == "oldest":
            filtered_reports.reverse()  # Reverse to get oldest first (ASC)
        
        # Limit to 200 results
        rows = filtered_reports[:200]
        
        # Calculate statistics
        stats_dict = {
            'for_review': len([r for r in reports_data if r[4] == 'FOR LUPON REVIEW']),
            'reviewed': len([r for r in reports_data if r[4] == 'REVIEWED']),
            'paid': len([r for r in reports_data if str(r[3]).upper() == 'PAID']),
            'unpaid': len([r for r in reports_data if str(r[3]).upper() == 'UNPAID'])
        }

    # Add pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(rows, 10)  # 10 reports per page
    
    try:
        reports = paginator.page(page)
    except PageNotAnInteger:
        reports = paginator.page(1)
    except EmptyPage:
        reports = paginator.page(paginator.num_pages)

    execution_time = time.time() - start_time
    log.info(f"PERFORMANCE: report_list executed in {execution_time:.3f} seconds")
    print(f"🚀 REPORT_LIST PERFORMANCE: {execution_time:.3f} seconds")
    
    return render(
        request,
        "lupon_mem/report_list_fast.html",
        {
            "reports": reports,
            "rows": reports.object_list,  # Keep for backward compatibility
            "q": q_raw,
            "user_role": user_role,
            "LUPON_ROLES_LIST": LUPON_ROLES_LIST,
            "payment_options": payment_options,
            "blotter_options": blotter_options,
            "f_payment": f_payment,
            "f_blotter": f_blotter,
            "f_date_from": f_date_from,
            "f_date_to": f_date_to,
            "f_sort": f_sort,
            "stats": stats_dict,
            "execution_time": f"{execution_time:.3f}s",
            "page_path": f"{user_role} / Blotter Reports",
            "page_title": "Blotter Reports",
        },
    )




@session_login_required
@role_required(*LUPON_ROLES)
def report_new(request: HttpRequest):
    if request.method == "GET":
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
        return render(request, "lupon_mem/report_new.html", {
            'page_path': f'{user_role} / New Report',
            'page_title': 'New Report'
        })

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    # Get form data
    incident_subject = (request.POST.get("incident_subject") or "").strip()
    incident_date = (request.POST.get("incident_date") or "").strip()
    incident_time = (request.POST.get("incident_time") or "").strip()
    incident_desc = (request.POST.get("incident_desc") or "").strip()

    # helpers
    def _toi(x):
        try:
            return int(x) if x not in (None, "",) else None
        except (TypeError, ValueError):
            return None

    def _tof(x):
        try:
            return float(x) if x not in (None, "",) else None
        except (TypeError, ValueError):
            return None

    complainant_id = _toi(request.POST.get("complainant_id"))
    respondent_ids = [_toi(x) for x in (request.POST.get("respondent_ids") or "").split(",")]
    respondent_ids = [x for x in respondent_ids if x]

    # address fields coming from the map picker
    incident_address_id = _toi(request.POST.get("incident_address_id"))

    lat = _tof(request.POST.get("incident_lat"))
    lng = _tof(request.POST.get("incident_lng"))

    map_street    = (request.POST.get("map_street") or "").strip() or None
    map_purok     = (request.POST.get("map_purok") or "").strip() or None  # e.g. "KANIPAAN (S01)" OR "KANIPAAN"
    map_barangay  = (request.POST.get("map_barangay") or "").strip() or None
    map_city      = (request.POST.get("map_city") or "").strip() or None

    # If no explicit address_id was provided, try to create one from the map fields
    if not incident_address_id and (lat is not None and lng is not None):
        with connection.cursor() as cur:
            # Resolve purok_sitio_id from a name like "KANIPAAN (S01)" or just "KANIPAAN"
            purok_name_for_lookup = None
            if map_purok:
                # pull out the part before " (" if present
                purok_name_for_lookup = map_purok.split(" (", 1)[0].strip()

            v_purok_sitio_id = None
            if purok_name_for_lookup:
                cur.execute(
                    """
                    SELECT ps.purok_sitio_id
                      FROM purok_sitio ps
                     WHERE upper(trim(ps.purok_sitio_name)) = upper(trim(%s))
                     LIMIT 1
                    """,
                    [purok_name_for_lookup],
                )
                row = cur.fetchone()
                if row:
                    v_purok_sitio_id = row[0]

            # Uppercase like your PL/pgSQL does
            up = lambda s: s.upper() if isinstance(s, str) else s
            up_street   = up(map_street)
            up_brgy     = up(map_barangay)
            up_city     = up(map_city)

            # Insert the address (allow some fields to be NULL if not available)
            cur.execute(
                """
                INSERT INTO addresss (latitude, longitude, street, barangay, city, purok_sitio_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING address_id
                """,
                [lat, lng, up_street, up_brgy, up_city, v_purok_sitio_id],
            )
            incident_address_id = cur.fetchone()[0]

    # Now create the blotter report using the (possibly newly created) address_id
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT create_blotter_report(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            """,
            [
                complainant_id,  # p_reported_by (person who reported)
                incident_subject,
                incident_desc,
                incident_date,
                incident_time,
                incident_address_id,
                complainant_id,  # p_complainant_id
                respondent_ids if respondent_ids else None,
                None,  # evidence jsonb
                staff_id,  # p_staff_id for set_report_status
            ],
        )
        report_id = cur.fetchone()[0]
        
        # Get staff name and person names for logging
        staff_name = None
        complainant_name = None
        respondent_names = []
        
        if staff_id:
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                [staff_id]
            )
            staff_row = cur.fetchone()
            staff_name = staff_row[0] if staff_row else None
        
        if complainant_id:
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', first_name, NULLIF(SUBSTRING(COALESCE(middle_name, '') FROM 1 FOR 1) || '.', '.'), last_name, NULLIF(suffix, ''))) FROM person WHERE person_id = %s",
                [complainant_id]
            )
            comp_row = cur.fetchone()
            complainant_name = comp_row[0] if comp_row else None
        
        if respondent_ids:
            for resp_id in respondent_ids:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', first_name, NULLIF(SUBSTRING(COALESCE(middle_name, '') FROM 1 FOR 1) || '.', '.'), last_name, NULLIF(suffix, ''))) FROM person WHERE person_id = %s",
                    [resp_id]
                )
                resp_row = cur.fetchone()
                if resp_row and resp_row[0]:
                    respondent_names.append(resp_row[0])
        
        # Build human-readable message
        message = f"{staff_name or f'Staff ID {staff_id}'} filed blotter report #{report_id} – {incident_subject or '(no subject)'}"
        if complainant_name:
            message += f" (complainant: {complainant_name}"
            if respondent_names:
                message += f", respondent(s): {', '.join(respondent_names)}"
            message += ")"
        elif respondent_names:
            message += f" (respondent(s): {', '.join(respondent_names)})"
        
        if incident_address_id:
            message += " with location"
        
        # Log the report creation
        blotter_log_event(
            action="CREATE",
            table_affected="blotter_report",
            record_affected_id=report_id,
            details=message,
            performer_staff_id=staff_id
        )

    messages.success(request, f"Report #{report_id} filed.")
    return redirect("lupon_mem:report_list")



@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def report_confirm(request: HttpRequest, report_id: int):
    if request.method == "GET":
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip()

        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT br.blotter_report_id, br.incident_subject, br.incident_desc,
                       br.incident_date, br.incident_time
                  FROM blotter_report br
                 WHERE br.blotter_report_id=%s
                """,
                [report_id],
            )
            rpt = cur.fetchone()
            if not rpt:
                return HttpResponseBadRequest("Report not found.")

            cur.execute(
                """
                SELECT p.person_id, p.first_name || ' ' || p.last_name AS name, 'COMPLAINANT' AS role
                  FROM complainant_report cr JOIN person p ON p.person_id=cr.person_id
                 WHERE cr.blotter_report_id=%s
                UNION ALL
                SELECT p.person_id, p.first_name || ' ' || p.last_name, 'RESPONDENT'
                  FROM respondent_report rr JOIN person p ON p.person_id=rr.person_id
                 WHERE rr.blotter_report_id=%s
                """,
                [report_id, report_id],
            )
            parties = cur.fetchall()

            cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
            complaint_titles = cur.fetchall()
            cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
            case_natures = cur.fetchall()
            cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
            settlements = cur.fetchall()

            # Server-side default case name (fallback if JS off)
            cur.execute(
                """
                SELECT p.last_name
                  FROM complainant_report cr
                  JOIN person p ON p.person_id = cr.person_id
                 WHERE cr.blotter_report_id=%s
                 ORDER BY p.last_name, p.first_name
                 LIMIT 1
                """,
                [report_id],
            )
            row_c = cur.fetchone()
            c_last = (row_c and (row_c[0] or "").strip()) or ""

            cur.execute(
                """
                SELECT p.last_name
                  FROM respondent_report rr
                  JOIN person p ON p.person_id = rr.person_id
                 WHERE rr.blotter_report_id=%s
                 ORDER BY p.last_name, p.first_name
                 LIMIT 1
                """,
                [report_id],
            )
            row_r = cur.fetchone()
            r_last = (row_r and (row_r[0] or "").strip()) or ""

            initial_case_name = f"{c_last} vs {r_last}" if (c_last and r_last) else "People vs"

        ctx = {
            "rpt": rpt,
            "parties": parties,
            "complaint_titles": complaint_titles,
            "case_natures": case_natures,
            "settlement_statuses": settlements,
            "report_id": report_id,
            "user_role": user_role,
            "initial_case_name": initial_case_name,
            'page_path': f'{user_role} / Confirm & Open Case',
            'page_title': 'Confirm & Open Case',
        }
        return render(request, "lupon_mem/report_confirm.html", ctx)

    # ---------- POST ----------
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    if not staff_id:
        messages.error(request, "Session expired. Please login again.")
        return redirect("lupon_mem:report_confirm", report_id=report_id)

    def _default_case_name(cur) -> str:
        # compute a basic default if the client didn't send case_name
        cur.execute(
            """
            SELECT coalesce(c_last,''), coalesce(r_last,'')
            FROM (
              SELECT
                (SELECT p.last_name
                   FROM complainant_report cr
                   JOIN person p ON p.person_id = cr.person_id
                  WHERE cr.blotter_report_id=%s
                  ORDER BY p.last_name, p.first_name
                  LIMIT 1) AS c_last,
                (SELECT p.last_name
                   FROM respondent_report rr
                   JOIN person p ON p.person_id = rr.person_id
                  WHERE rr.blotter_report_id=%s
                  ORDER BY p.last_name, p.first_name
                  LIMIT 1) AS r_last
            ) s
            """,
            [report_id, report_id],
        )
        row = cur.fetchone()
        c_last = (row and (row[0] or "").strip()) or ""
        r_last = (row and (row[1] or "").strip()) or ""
        return f"{c_last} vs {r_last}" if (c_last and r_last) else "People vs"

    # Pull fields
    case_name = (request.POST.get("case_name") or "").strip()
    complaint_title_id = _toi(request.POST.get("complaint_title_id"))
    case_nature_id = _toi(request.POST.get("case_nature_id"))
    settlement_status_id = _toi(request.POST.get("settlement_status_id"))

    # fill case_name if blank
    if not case_name:
        with connection.cursor() as cur:
            case_name = _default_case_name(cur)

    with_payment = (request.POST.get("with_payment") == "on")
    payment_receipt = (request.POST.get("payment_receipt") or "").strip() or None
    payment_amount = request.POST.get("payment_amount")
    try:
        payment_amount = float(payment_amount) if payment_amount not in (None, "",) else 0.0
    except ValueError:
        payment_amount = 0.0
    payment_status = (request.POST.get("payment_status") or "PAID").strip().upper()
    paid_by_person_id = _toi(request.POST.get("paid_by_person_id"))

    if not complaint_title_id or not case_nature_id or not settlement_status_id:
        messages.error(request, "Please select Complaint Title, Case Nature, and Settlement Status.")
        return redirect("lupon_mem:report_confirm", report_id=report_id)

    if with_payment and not payment_receipt:
        messages.error(request, "Enter an OR / Receipt No. to record the payment.")
        return redirect("lupon_mem:report_confirm", report_id=report_id)

    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT confirm_report_and_open_case(
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s
                )
                """,
                [
                    report_id,
                    case_name,
                    complaint_title_id,
                    case_nature_id,
                    settlement_status_id,
                    staff_id,
                    with_payment,
                    payment_receipt,
                    payment_amount,
                    payment_status,
                    paid_by_person_id,
                ],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                messages.error(request, "Case could not be created.")
                return redirect("lupon_mem:report_confirm", report_id=report_id)
            case_id = int(row[0])
            
            # Log the case creation from report
            blotter_log_event(
                action="CREATE",
                table_affected="blotter_case",
                record_affected_id=case_id,
                details={
                    "source_report_id": report_id,
                    "case_name": case_name,
                    "complaint_title_id": complaint_title_id,
                    "case_nature_id": case_nature_id,
                    "with_payment": with_payment,
                    "payment_amount": float(payment_amount) if payment_amount else 0
                },
                performer_staff_id=staff_id
            )
    except DatabaseError as e:
        messages.error(request, f"Failed to create case: {e}")
        return redirect("lupon_mem:report_confirm", report_id=report_id)
    except Exception:
        messages.error(request, "Unexpected error while creating case.")
        return redirect("lupon_mem:report_confirm", report_id=report_id)

    messages.success(request, f"Case #{case_id} created.")
    return redirect("lupon_mem:case_detail", case_id=case_id)




# ------------------------------
# REVIEW (Lupon) – no Payment card; Approve/Decline here
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def report_review(request: HttpRequest, report_id: int):
    auth = request.session.get("auth") or {}
    role = (auth.get("role_name") or auth.get("role") or "").strip()

    with connection.cursor() as cur:
        # main report record
        cur.execute("""
            SELECT br.blotter_report_id,
                   COALESCE(br.incident_subject,'(no subject)') AS subj,
                   COALESCE(br.incident_desc,'') AS descr,
                   to_char(br.date_time_reported AT TIME ZONE 'Asia/Manila','Month DD, YYYY HH12:MI AM') AS reported_at,
                   COALESCE(ps.payment_status_name, '—') AS pay_status,
                   COALESCE(
                     NULLIF(
                       trim(
                         concat_ws(', ',
                           NULLIF(a.street, ''),
                           NULLIF(pks.purok_sitio_name, ''),
                           NULLIF(a.barangay, ''),
                           NULLIF(a.city, '')
                         )
                       ), ''
                     ), '—'
                   ) AS incident_address,
                   a.latitude,
                   a.longitude,
                   br.temp_complaint_title_id,
                   br.temp_case_nature_id,
                   ct.complaint_title_name,
                   cn.case_name,
                   to_char(br.incident_date, 'Month DD, YYYY') AS incident_date
            FROM blotter_report br
            LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
            LEFT JOIN addresss a        ON a.address_id = br.incident_address_id
            LEFT JOIN purok_sitio pks   ON pks.purok_sitio_id = a.purok_sitio_id
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = br.temp_complaint_title_id
            LEFT JOIN case_nature cn     ON cn.case_nature_id = br.temp_case_nature_id
            WHERE br.blotter_report_id=%s
        """, [report_id])
        rpt = cur.fetchone()
        if not rpt:
            return HttpResponseBadRequest("Report not found.")
        
        print(f"[DEBUG][REVIEW] Report data: temp_complaint_title_id={rpt[8]}, temp_case_nature_id={rpt[9]}")
        print(f"[DEBUG][REVIEW] Names: complaint_title_name='{rpt[10]}', case_name='{rpt[11]}'")
        
        # Additional debug: verify the data we got
        print(f"[DEBUG][REVIEW] Full report tuple length: {len(rpt)}")
        for i, val in enumerate(rpt):
            print(f"[DEBUG][REVIEW] rpt[{i}] = {val}")

        # parties
        cur.execute("""
            SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name, 'COMPLAINANT' AS role
              FROM complainant_report cr
              JOIN person p ON p.person_id = cr.person_id
             WHERE cr.blotter_report_id=%s
            UNION ALL
            SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')), 'RESPONDENT'
              FROM respondent_report rr
              JOIN person p ON p.person_id = rr.person_id
             WHERE rr.blotter_report_id=%s
             ORDER BY role, name
        """, [report_id, report_id])
        parties = cur.fetchall()
        
        # Check if there's at least one respondent
        has_respondent = any(p[2].upper() == 'RESPONDENT' for p in parties)

        # picklist data
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
        case_natures = cur.fetchall()
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
        settlements = cur.fetchall()

        # latest review trail entry (who/when/remarks)
        # Debug: get ALL entries first
        cur.execute("""
            SELECT rsd.report_status_detail_id, rsd.verification_date, rs.report_status_name, rsd.remarks
            FROM report_status_detail rsd
            LEFT JOIN report_status rs ON rs.report_status_id = rsd.report_status_id
            WHERE rsd.blotter_report_id = %s
            ORDER BY rsd.verification_date DESC
        """, [report_id])
        all_reviews = cur.fetchall()
        print(f"[DEBUG] All reviews for report {report_id}: {all_reviews}")
        
        cur.execute("""
            SELECT
              rs.report_status_name      AS action,             -- APPROVED / DECLINED / REVIEWED ...
              rsd.remarks                AS remarks,            -- reason text (if any)
              to_char(rsd.verification_date AT TIME ZONE 'Asia/Manila','Month DD, YYYY HH12:MI AM') AS acted_at,
              s.staff_id,
              trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS reviewer_name
            FROM report_status_detail rsd
            LEFT JOIN report_status rs ON rs.report_status_id = rsd.report_status_id
            LEFT JOIN staff s           ON s.staff_id = rsd.processed_by_id
            LEFT JOIN person p          ON p.person_id = s.person_id
            WHERE rsd.blotter_report_id = %s
            ORDER BY rsd.verification_date DESC, rsd.report_status_detail_id DESC
            LIMIT 1
        """, [report_id])
        latest_review = cur.fetchone()
        print(f"[DEBUG] Latest review selected: {latest_review}")

    pay_status = (rpt[4] or "—").upper()
    # is reviewed if payment status is conclusive OR we have an approve/decline entry
    action = (latest_review[0] if latest_review else "") or ""
    is_reviewed = pay_status in ("PAID", "UNPAID", "DECLINED") or action in ("APPROVED", "DECLINED")

    ctx = {
        "report": rpt,
        "parties": parties,
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlements,
        "user_role": role,
        "LUPON_ROLES_LIST": LUPON_ROLES_LIST,
        "has_respondent": has_respondent,

        # review meta (safe-guard for None)
        "is_reviewed": is_reviewed,
        "review_action": action,
        "reviewed_by": (latest_review[4] if latest_review else None),
        "reviewed_at": (latest_review[2] if latest_review else None),
        "review_remarks": (latest_review[1] if latest_review else None),
        
        # stored selections (if approved) - complaint_title_name is at index 10, case_name is at index 11
        "selected_complaint_title": rpt[10] if len(rpt) > 10 else None,  # complaint_title_name
        "selected_case_nature": rpt[11] if len(rpt) > 11 else None,      # case_name
        
        # incident date is at index 12
        "incident_date": rpt[12] if len(rpt) > 12 else None,
        
        # Debug what we're passing to template
        "debug_complaint_title": rpt[10] if len(rpt) > 10 else "None",
        "debug_case_nature": rpt[11] if len(rpt) > 11 else "None",
        'page_path': f'{role} / Review Report',
        'page_title': 'Review Blotter Report',
    }
    return render(request, "lupon_mem/report_review.html", ctx)


@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def report_update_respondents(request: HttpRequest, report_id: int):
    """Update respondents for a blotter report"""
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        return HttpResponseBadRequest("Missing staff id.")

    # Get respondent IDs from form
    respondent_ids_str = (request.POST.get("respondent_ids") or "").strip()
    respondent_ids = [_toi(x) for x in respondent_ids_str.split(",") if x.strip()]
    respondent_ids = [x for x in respondent_ids if x]

    if not respondent_ids:
        messages.error(request, "Please select at least one respondent.")
        return redirect("lupon_mem:report_review", report_id=report_id)

    try:
        with connection.cursor() as cur:
            # Call the update function
            cur.execute(
                "SELECT update_blotter_report(%s, %s)",
                [report_id, respondent_ids]
            )
            result = cur.fetchone()[0]
            
            # Get respondent names for logging
            respondent_names = []
            for resp_id in respondent_ids:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', first_name, NULLIF(SUBSTRING(COALESCE(middle_name, '') FROM 1 FOR 1) || '.', '.'), last_name, NULLIF(suffix, ''))) FROM person WHERE person_id = %s",
                    [resp_id]
                )
                resp_row = cur.fetchone()
                if resp_row and resp_row[0]:
                    respondent_names.append(resp_row[0])
            
            # Get staff name for logging
            staff_name = None
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                [staff_id]
            )
            staff_row = cur.fetchone()
            staff_name = staff_row[0] if staff_row else None
            
            # Log the update
            message = f"{staff_name or f'Staff ID {staff_id}'} updated respondents for blotter report #{report_id}"
            if respondent_names:
                message += f" (respondent(s): {', '.join(respondent_names)})"
            
            blotter_log_event(
                action="UPDATE",
                table_affected="blotter_report",
                record_affected_id=report_id,
                details=message,
                performer_staff_id=staff_id,
                field_changed="respondents",
                new_value=", ".join(respondent_names) if respondent_names else "N/A"
            )
            
        messages.success(request, "Respondents updated successfully.")
    except Exception as e:
        messages.error(request, f"Failed to update respondents: {e}")
    
    return redirect("lupon_mem:report_review", report_id=report_id)


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def report_mark_paid(request: HttpRequest, report_id: int):
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        return HttpResponseBadRequest("Missing staff id.")

    paid_by_person_id = _toi(request.POST.get("paid_by_person_id"))
    date_filed = _to_none_if_blank(request.POST.get("date_filed"))
    time_filed = _to_none_if_blank(request.POST.get("time_filed"))
    blotter_case_num = _to_none_if_blank(request.POST.get("blotter_case_num"))
    
    if not paid_by_person_id:
        messages.error(request, "Please select who paid.")
        return redirect("lupon_mem:report_review", report_id=report_id)
    
    if not date_filed or not time_filed:
        messages.error(request, "Please provide date and time filed.")
        return redirect("lupon_mem:report_review", report_id=report_id)

    try:
        with connection.cursor() as cur:
            # Get report details for case creation
            cur.execute(
                "SELECT temp_complaint_title_id, temp_case_nature_id FROM blotter_report WHERE blotter_report_id = %s",
                [report_id]
            )
            temp_row = cur.fetchone()
            complaint_title_id = temp_row[0] if temp_row else None
            case_nature_id = temp_row[1] if temp_row else None
            
            # Get case name from parties
            cur.execute(
                "SELECT p.last_name FROM complainant_report cr JOIN person p ON p.person_id = cr.person_id WHERE cr.blotter_report_id = %s LIMIT 1",
                [report_id]
            )
            c_row = cur.fetchone()
            c_last = c_row[0] if c_row else "Complainant"
            
            cur.execute(
                "SELECT p.last_name FROM respondent_report rr JOIN person p ON p.person_id = rr.person_id WHERE rr.blotter_report_id = %s LIMIT 1",
                [report_id]
            )
            r_row = cur.fetchone()
            r_last = r_row[0] if r_row else "Respondent"
            
            case_name = f"{c_last} vs {r_last}"
            
            # Get settlement status ID for ONGOING
            cur.execute("SELECT settlement_status_id FROM settlement_status WHERE UPPER(settlement_status_name) = 'ONGOING' LIMIT 1")
            ss_row = cur.fetchone()
            settlement_status_id = ss_row[0] if ss_row else 1
            
            # Create case using confirm_report_and_open_case with date/time
            cur.execute(
                "SELECT confirm_report_and_open_case(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    report_id,
                    case_name,
                    complaint_title_id,
                    case_nature_id,
                    settlement_status_id,
                    staff_id,
                    True,  # with_payment
                    None,  # payment_receipt
                    150.00,  # payment_amount
                    "PAID",  # payment_status
                    paid_by_person_id,
                    "ESCALATED TO CASE",
                    "Report marked as paid and escalated to case",
                    date_filed,
                    time_filed,
                    blotter_case_num
                ]
            )
            case_id = cur.fetchone()[0]
            
            # Ensure payment status is set to PAID
            cur.execute(
                "UPDATE blotter_report SET payment_status_id = (SELECT payment_status_id FROM payment_status WHERE payment_status_name = 'PAID') WHERE blotter_report_id = %s",
                [report_id]
            )
            
            # Ensure report status is ESCALATED TO CASE
            cur.execute(
                """UPDATE blotter_report 
                   SET current_status_id = (SELECT report_status_id FROM report_status WHERE report_status_name = 'ESCALATED TO CASE')
                   WHERE blotter_report_id = %s""",
                [report_id]
            )
            
            # Set case state to OPEN
            cur.execute(
                "UPDATE blotter_case SET case_state_id = 1 WHERE blotter_case_id = %s",
                [case_id]
            )
            
            # Get case number and payer name for display
            cur.execute(
                "SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id = %s",
                [case_id]
            )
            case_num = cur.fetchone()[0] if cur.rowcount else None
            
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', first_name, last_name)) FROM person WHERE person_id = %s",
                [paid_by_person_id]
            )
            payer_name = cur.fetchone()[0] if cur.rowcount else None
            
            blotter_log_event(
                action="CREATE",
                table_affected="blotter_case",
                record_affected_id=case_id,
                details=f"Case created from report #{report_id}, marked as PAID (paid by: {payer_name or 'Unknown'})",
                performer_staff_id=staff_id
            )
        
        messages.success(request, f"Report marked as paid and case {case_num or f'#{case_id}'} created (Filed: {date_filed} {time_filed}).")
        return redirect("lupon_mem:case_detail", case_id=case_id)
    except Exception as e:
        messages.error(request, f"Failed: {e}")
        return redirect("lupon_mem:report_review", report_id=report_id)


# APPROVE (Lupon -> set UNPAID via DB func)
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def report_approve(request: HttpRequest, report_id: int):
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        return HttpResponseBadRequest("Missing staff id.")

    # DEBUG: show what form data is being passed
    case_name = request.POST.get('case_name')
    complaint_title_id = _toi(request.POST.get('complaint_title_id'))
    case_nature_id = _toi(request.POST.get('case_nature_id'))
    settlement_status_id = _toi(request.POST.get('settlement_status_id'))
    
    print(f"\n[DEBUG][APPROVE] Form data: case_name={case_name}, complaint_title_id={complaint_title_id}, case_nature_id={case_nature_id}, settlement_status_id={settlement_status_id}")
    print("[DEBUG][APPROVE] report_id=", report_id, " staff_id=", staff_id)
    
    # Store selected values in session for pay-open flow
    if complaint_title_id:
        request.session['selected_complaint_title_id'] = complaint_title_id
    if case_nature_id:
        request.session['selected_case_nature_id'] = case_nature_id
    request.session.modified = True
    print(f"[DEBUG][APPROVE] Stored in session: complaint_title_id={complaint_title_id}, case_nature_id={case_nature_id}")
    try:
        with connection.cursor() as cur:
            print("[DEBUG][APPROVE] SQL → approve_report_set_unpaid(%s,%s,%s,%s,%s)")
            cur.execute(
                "SELECT approve_report_set_unpaid(%s,%s,%s,%s,%s)",
                [report_id, staff_id, "Approved for case payment", complaint_title_id, case_nature_id],
            )
            res = cur.fetchone()
            print("[DEBUG][APPROVE] DB result:", res)
            print(f"[DEBUG][APPROVE] Stored case details via function: complaint_title_id={complaint_title_id}, case_nature_id={case_nature_id}")
            
            # Get staff name and complaint/case nature names for logging
            staff_name = None
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                [staff_id]
            )
            staff_row = cur.fetchone()
            staff_name = staff_row[0] if staff_row else None
            
            complaint_title_name = None
            case_nature_name = None
            if complaint_title_id:
                cur.execute("SELECT complaint_title_name FROM complaint_title WHERE complaint_title_id = %s", [complaint_title_id])
                ct_row = cur.fetchone()
                complaint_title_name = ct_row[0] if ct_row else None
            if case_nature_id:
                cur.execute("SELECT case_name FROM case_nature WHERE case_nature_id = %s", [case_nature_id])
                cn_row = cur.fetchone()
                case_nature_name = cn_row[0] if cn_row else None
            
            # Build human-readable message
            message = f"{staff_name or f'Staff ID {staff_id}'} approved blotter report #{report_id} for case payment"
            if complaint_title_name:
                message += f" (Complaint: {complaint_title_name}"
                if case_nature_name:
                    message += f", Nature: {case_nature_name}"
                message += ")"
            
            # Log the report approval
            blotter_log_event(
                action="UPDATE",
                table_affected="blotter_report",
                record_affected_id=report_id,
                details=message,
                performer_staff_id=staff_id,
                field_changed="payment_status",
                new_value="UNPAID"
            )
    except Exception as e:
        print("[DEBUG][APPROVE][ERROR]", e)
        raise

    return redirect("lupon_mem:report_review", report_id=report_id)


# ------------------------------
# DECLINE (Lupon)
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def report_decline(request: HttpRequest, report_id: int):
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        return HttpResponseBadRequest("Missing staff id.")

    reason = (request.POST.get("reason") or "").strip() or "Declined by Lupon"

    # DEBUG: same style as your approve view
    print("\n[DEBUG][DECLINE] report_id=", report_id, " staff_id=", staff_id, " reason=", reason)
    try:
        with connection.cursor() as cur:
            print("[DEBUG][DECLINE] SQL → decline_report_set_declined(%s,%s,%s)")
            cur.execute(
                "SELECT decline_report_set_declined(%s,%s,%s)",
                [report_id, staff_id, reason],
            )
            res = cur.fetchone()  # may be None; just echo for symmetry
            print("[DEBUG][DECLINE] DB result:", res)
            
            # Get staff name for logging
            staff_name = None
            cur.execute(
                "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                [staff_id]
            )
            staff_row = cur.fetchone()
            staff_name = staff_row[0] if staff_row else None
            
            # Build human-readable message
            message = f"{staff_name or f'Staff ID {staff_id}'} declined blotter report #{report_id}"
            if reason and reason != "Declined by Lupon":
                message += f" (Reason: {reason})"
            
            # Log the report decline
            blotter_log_event(
                action="UPDATE",
                table_affected="blotter_report",
                record_affected_id=report_id,
                details=message,
                performer_staff_id=staff_id,
                field_changed="payment_status",
                new_value="DECLINED"
            )
    except Exception as e:
        print("[DEBUG][DECLINE][ERROR]", e)
        raise

    return redirect("lupon_mem:report_review", report_id=report_id)



@session_login_required
@role_required("barangay treasurer")
def report_payment_details(request: HttpRequest, report_id: int):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT p.*, br.incident_subject, br.date_time_reported
            FROM rpc_report_payment_latest(%s) p,
                 blotter_report br
            WHERE br.blotter_report_id = %s
            """,
            [report_id, report_id]
        )
        row = cur.fetchone()
        if not row:
            return HttpResponseBadRequest("Payment or report not found.")
        
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
    
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    return render(request, "lupon_mem/report_payment_details.html", {
        "report": (data['blotter_report_id'], data['incident_subject'], data['date_time_reported']),
        "payment": data,
        'page_path': f'{user_role} / Payment Details',
        'page_title': 'Payment Details'
    })


@session_login_required
@role_required("barangay treasurer")
def report_pay_and_open_case(request: HttpRequest, report_id: int):
    """
    Treasurer flow:
      • Shows report details (read-only) + read-only case fields prefilled by sensible defaults
      • Only "Record payment now" card is editable
      • On submit, uses confirm_report_and_open_case(...)
    """
    # ---- small helpers kept local to avoid scope/import issues ----
    def _toi(x):
        try:
            return int(x) if (x is not None and str(x).strip() and str(x).strip() != "0") else None
        except Exception:
            return None

    def _to_decimal(x, default="0"):
        from decimal import Decimal as _Dec
        try:
            return _Dec(str(x)) if (x is not None and str(x).strip()) else _Dec(default)
        except Exception:
            return _Dec(default)

    def _make_default_or(rpt_id: int) -> str:
        from datetime import datetime
        return f"OR-{datetime.now():%Y%m%d-%H%M%S}-{rpt_id:05d}"

    # -------- GET: build read-only page --------
    if request.method == "GET":
        with connection.cursor() as cur:
            # exact report details
            cur.execute(
                """
                SELECT br.blotter_report_id,
                       COALESCE(br.incident_subject,'(no subject)') AS subj,
                       to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
                       COALESCE(br.incident_desc,'') AS desc
                  FROM blotter_report br
                 WHERE br.blotter_report_id = %s
                """,
                [report_id],
            )
            rpt = cur.fetchone()
            if not rpt:
                return HttpResponseBadRequest("Report not found.")

            # parties (COMPLAINANT / RESPONDENT)
            cur.execute(
                """
                SELECT p.person_id,
                       trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name,
                       'COMPLAINANT' AS role
                  FROM complainant_report cr
                  JOIN person p ON p.person_id = cr.person_id
                 WHERE cr.blotter_report_id = %s
                UNION ALL
                SELECT p.person_id,
                       trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name,
                       'RESPONDENT'
                  FROM respondent_report rr
                  JOIN person p ON p.person_id = rr.person_id
                 WHERE rr.blotter_report_id = %s
                 ORDER BY role, name
                """,
                [report_id, report_id],
            )
            parties = cur.fetchall()

            # lookups
            cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
            complaint_titles = cur.fetchall()

            cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
            case_natures = cur.fetchall()

            cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
            settlements = cur.fetchall()

            cur.execute("SELECT payment_status_name FROM payment_status ORDER BY 1")
            payment_statuses = [r[0] for r in cur.fetchall()]

        # derive case name "Lastname vs. Lastname" (fallback "People vs.")
        def _role_first_name(role_label: str) -> str | None:
            for pid, nm, rl in parties:
                if str(rl).upper() == role_label.upper():
                    return (nm or "").strip() or None
            return None

        cmp_name = _role_first_name("COMPLAINANT")
        rsp_name = _role_first_name("RESPONDENT")
        initial_case_name = "People vs."
        if cmp_name and rsp_name:
            # try last tokens
            c_last = cmp_name.split()[-1]
            r_last = rsp_name.split()[-1]
            initial_case_name = f"{c_last} vs. {r_last}"

        # Get selected values from database (stored during approve) or use defaults
        with connection.cursor() as cur:
            cur.execute(
                "SELECT temp_complaint_title_id, temp_case_nature_id FROM blotter_report WHERE blotter_report_id = %s",
                [report_id]
            )
            temp_row = cur.fetchone()
            ct_id = temp_row[0] if temp_row and temp_row[0] else None
            cn_id = temp_row[1] if temp_row and temp_row[1] else None
            print(f"[DEBUG][PAY_OPEN] Retrieved from DB: complaint_title_id={ct_id}, case_nature_id={cn_id}")
        
        # Find names for the selected IDs
        ct_name = ""
        cn_name = ""
        
        if ct_id:
            for cid, cname in complaint_titles:
                if cid == ct_id:
                    ct_name = cname
                    break
        else:
            # Use first as default if no session data
            ct_id, ct_name = (complaint_titles[0][0], complaint_titles[0][1]) if complaint_titles else (None, "")
            
        if cn_id:
            for nid, nname in case_natures:
                if nid == cn_id:
                    cn_name = nname
                    break
        else:
            # Use first as default if no session data
            cn_id, cn_name = (case_natures[0][0], case_natures[0][1]) if case_natures else (None, "")

        # settlement defaults to ONGOING
        st_id, st_name = (None, "")
        for sid, sname in settlements:
            if str(sname).upper() == "ONGOING":
                st_id, st_name = sid, sname
                break
        if st_id is None and settlements:
            st_id, st_name = settlements[0]

        # DEBUG: what the page will show as read-only defaults
        print("\n[DEBUG][PAY-OPEN][GET] report:", rpt)
        print("[DEBUG][PAY-OPEN][GET] case defaults:",
            {"case_name": initial_case_name,
            "complaint_title_id": ct_id, "complaint_title_name": ct_name,
            "case_nature_id": cn_id, "case_nature_name": cn_name,
            "settlement_status_id": st_id, "settlement_status_name": st_name,
            "default_or": _make_default_or(report_id), "default_amount": "150.00"})

        ctx = {
            "page_title": "Confirm Payment & Open Case",
            "report": rpt,
            "parties": parties,

            # read-only case values (also mirrored as hidden inputs in the template)
            "case_name": initial_case_name,
            "complaint_title_id": ct_id,
            "complaint_title_name": ct_name,
            "case_nature_id": cn_id,
            "case_nature_name": cn_name,
            "settlement_status_id": st_id,
            "settlement_status_name": st_name,

            # lists kept only for safety; UI won't expose them for editing
            "complaint_titles": complaint_titles,
            "case_natures": case_natures,
            "settlement_statuses": settlements,

            # payment UI
            "payment_statuses": payment_statuses,
            "default_or": _make_default_or(report_id),
            "default_amount": "150.00",
        }
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
        ctx.update({
            'page_path': f'{user_role} / Pay & Open Case',
            'page_title': 'Pay & Open Case'
        })
        return render(request, "lupon_mem/report_pay.html", ctx)

    # -------- POST: consume hidden read-only values and optional payment --------
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    if not staff_id:
        messages.error(request, "Session expired. Please login again.")
        return redirect("lupon_mem:report_pay_and_open_case", report_id=report_id)

    case_name            = (request.POST.get("case_name") or "").strip() or "Untitled Case"
    complaint_title_id   = _toi(request.POST.get("complaint_title_id"))
    case_nature_id       = _toi(request.POST.get("case_nature_id"))
    settlement_status_id = _toi(request.POST.get("settlement_status_id"))
    date_filed           = (request.POST.get("date_filed") or "").strip() or None
    time_filed           = (request.POST.get("time_filed") or "").strip() or None

    # payment toggle + details
    with_payment      = (request.POST.get("with_payment") == "on")
    payment_receipt   = (request.POST.get("payment_receipt") or "").strip()
    payment_amount    = _to_decimal(request.POST.get("payment_amount"), default="0")
    payment_status    = (request.POST.get("payment_status") or "PAID").strip()
    paid_by_person_id = _toi(request.POST.get("paid_by_person_id"))

    # if recording payment, force defaults where needed
    if with_payment:
        if not payment_receipt:
            payment_receipt = _make_default_or(report_id)
        if not payment_status:
            payment_status = "PAID"
    else:
        # when NOT recording payment, ensure we don't pass stray values
        payment_receipt = None
        payment_amount = None
        payment_status = "UNPAID"
        paid_by_person_id = None

    args = [
        report_id,
        case_name,
        complaint_title_id,
        case_nature_id,
        settlement_status_id,
        staff_id,

        # payment group
        with_payment,
        payment_receipt,
        payment_amount,
        payment_status,
        paid_by_person_id,

        # status after
        "ESCALATED TO CASE",
        "Report converted to case",
        
        # date/time filed
        date_filed,
        time_filed,
    ]
    print("[DEBUG][PAY-OPEN][POST] SQL → confirm_report_and_open_case(...) args:", args)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT confirm_report_and_open_case(
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s
            )""",
            args,
        )
        case_id = cur.fetchone()[0]
        
        # Ensure payment status is set and case is escalated
        if with_payment and payment_status:
            cur.execute(
                "UPDATE blotter_report SET payment_status_id = (SELECT payment_status_id FROM payment_status WHERE payment_status_name = %s) WHERE blotter_report_id = %s",
                [payment_status, report_id]
            )
        
        # Set case state to OPEN (case_state_id = 1)
        cur.execute(
            "UPDATE blotter_case SET case_state_id = 1 WHERE blotter_case_id = %s",
            [case_id]
        )
        
        # Ensure report status is ESCALATED TO CASE
        cur.execute(
            """UPDATE blotter_report 
               SET current_status_id = (SELECT report_status_id FROM report_status WHERE report_status_name = 'ESCALATED TO CASE')
               WHERE blotter_report_id = %s""",
            [report_id]
        )
            
        # Log the payment and case creation
        blotter_log_event(
            action="CREATE",
            table_affected="blotter_case",
            record_affected_id=case_id,
            details={
                "source_report_id": report_id,
                "case_name": case_name,
                "with_payment": with_payment,
                "payment_status": payment_status if with_payment else None,
                "payment_amount": float(payment_amount) if with_payment and payment_amount else 0,
                "payment_receipt": payment_receipt if with_payment else None
            },
            performer_staff_id=staff_id
        )
        
        if with_payment:
            blotter_log_event(
                action="UPDATE",
                table_affected="blotter_report",
                record_affected_id=report_id,
                details={
                    "payment_recorded": True,
                    "payment_amount": float(payment_amount) if payment_amount else 0,
                    "payment_receipt": payment_receipt
                },
                performer_staff_id=staff_id,
                field_changed="payment_status",
                new_value=payment_status
            )

    messages.success(request, f"Case #{case_id} created.")
    return redirect("lupon_mem:case_detail", case_id=case_id)


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def update_case_state(request, case_id: int):
    case_state_id = _toi(request.POST.get("case_state_id"))
    remarks = (request.POST.get("remarks") or "").strip()
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    if not staff_id:
        messages.error(request, "Missing staff ID.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    if not case_state_id:
        messages.info(request, "No case state selected.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT update_case_status(
                      p_blotter_case_id := %s,
                      p_new_state_id    := %s,
                      p_by_staff_id     := %s,
                      p_note            := %s
                    )
                    """,
                    [case_id, case_state_id, staff_id, remarks or None],
                )
                changed = cur.fetchone()[0]
        if changed:
            messages.success(request, "Case state updated and logged.")
        else:
            messages.info(request, "No change (same state as before).")
    except Exception as e:
        messages.error(request, f"Failed to update case state: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def update_settlement_status(request, case_id: int):
    settlement_status_id = _toi(request.POST.get("settlement_status_id"))
    remarks = (request.POST.get("remarks") or "").strip()
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    if not staff_id:
        messages.error(request, "Missing staff ID.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    if not settlement_status_id:
        messages.info(request, "No settlement status selected.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT update_case_settlement_status(
                      p_blotter_case_id := %s,
                      p_new_status_id   := %s,
                      p_by_staff_id     := %s,
                      p_note            := %s
                    )
                    """,
                    [case_id, settlement_status_id, staff_id, remarks or None],
                )
                changed = cur.fetchone()[0]
        if changed:
            messages.success(request, "Settlement status updated and logged.")
        else:
            messages.info(request, "No change (same settlement status as before).")
    except Exception as e:
        messages.error(request, f"Failed to update settlement status: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)


@session_login_required
@require_POST
def store_session_values(request):
    """Store selected complaint title and case nature in session for pay-open flow"""
    import json
    try:
        data = json.loads(request.body)
        ct_id = data.get('complaint_title_id')
        cn_id = data.get('case_nature_id')
        print(f"[DEBUG][STORE_SESSION] Storing: complaint_title_id={ct_id}, case_nature_id={cn_id}")
        request.session['selected_complaint_title_id'] = ct_id
        request.session['selected_case_nature_id'] = cn_id
        request.session.modified = True
        return JsonResponse({'success': True})
    except Exception as e:
        print(f"[DEBUG][STORE_SESSION][ERROR] {e}")
        return JsonResponse({'success': False}, status=400)


@session_login_required
@role_required(*LUPON_ROLES)
def blotter_reports_menu(request: HttpRequest):
    """Display blotter reports menu"""
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    # Get filter options for modal
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()
    
    return render(request, "lupon_mem/blotter_reports_menu.html", {
        'complaint_titles': complaint_titles,
        'case_natures': case_natures,
        'page_path': f'{user_role} / Reports',
        'page_title': 'Reports'
    })


def add_barangay_header(elements, styles, report_title):
    """Add professional barangay header to PDF reports"""
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from datetime import datetime
    from django.conf import settings
    import os
    
    # Add centered logo
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1*inch, height=1*inch)
        logo_table = Table([[logo]], colWidths=[6*inch])
        logo_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        elements.append(logo_table)
        elements.append(Spacer(1, 10))
    
    # Republic of the Philippines header
    rp_style = ParagraphStyle('RPHeader', parent=styles['Normal'], fontSize=12, alignment=1, fontName='Helvetica-Bold')
    elements.append(Paragraph("Republic of the Philippines", rp_style))
    
    # Office header
    office_style = ParagraphStyle('OfficeHeader', parent=styles['Normal'], fontSize=11, alignment=1, fontName='Helvetica')
    # elements.append(Paragraph("Office of the Barangay Captain", office_style))
    
    # Barangay name
    brgy_style = ParagraphStyle('BrgyHeader', parent=styles['Normal'], fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=5)
    elements.append(Paragraph("BARANGAY SEÑOR SANTO NIÑO", brgy_style))
    
    # Address and contact info
    contact_style = ParagraphStyle(
        'ContactHeader',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        fontName='Helvetica'
    )
    elements.append(Paragraph("032 Legaspi Street, Cebu City", contact_style))
    elements.append(Paragraph("Telephone No. (032) 265-786/503-3115", contact_style))
    elements.append(Paragraph("E-mail Address: bss@hotmail.ph", contact_style))
    
    # Separator line
    elements.append(Spacer(1, 20))
    line_table = Table([['_' * 80]], colWidths=[6*inch])
    line_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(line_table)
    elements.append(Spacer(1, 20))
    
    # Report title
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    elements.append(Paragraph(report_title, title_style))
    
    # Date generated
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1
    )
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", date_style))
    elements.append(Spacer(1, 30))


@session_login_required
@role_required(*LUPON_ROLES)
def total_cases_by_status_report(request: HttpRequest):
    """Generate PDF report of total cases by status with filters"""
    if request.method == "GET":
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
        return render(request, "lupon_mem/total_cases_filters.html", {
            'page_path': f'{user_role} / Reports / Total Cases by Status',
            'page_title': 'Total Cases by Status Report'
        })
    
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch
    from io import BytesIO
    import calendar, os
    
    month = _toi(request.POST.get('month'))
    year = _toi(request.POST.get('year'))
    
    where_conditions = []
    params = []
    
    if month and year:
        where_conditions.append("EXTRACT(MONTH FROM bc.date_filed) = %s")
        where_conditions.append("EXTRACT(YEAR FROM bc.date_filed) = %s")
        params.extend([month, year])
    elif year:
        where_conditions.append("EXTRACT(YEAR FROM bc.date_filed) = %s")
        params.append(year)
    
    where_clause = " AND " + " AND ".join(where_conditions) if where_conditions else ""
    
    with connection.cursor() as cur:
        # Case state breakdown
        cur.execute(f"""
            SELECT cs.case_state_name, COUNT(bc.blotter_case_id) as case_count
            FROM case_state cs
            LEFT JOIN blotter_case bc ON bc.case_state_id = cs.case_state_id
            WHERE 1=1 {where_clause}
            GROUP BY cs.case_state_id, cs.case_state_name
            ORDER BY case_count DESC
        """, params)
        status_data = cur.fetchall()
        
        # Settlement status breakdown
        cur.execute(f"""
            SELECT ss.settlement_status_name, COUNT(bc.blotter_case_id) as case_count
            FROM settlement_status ss
            LEFT JOIN blotter_case bc ON bc.settlement_status_id = ss.settlement_status_id
            WHERE 1=1 {where_clause}
            GROUP BY ss.settlement_status_id, ss.settlement_status_name
            ORDER BY case_count DESC
        """, params)
        settlement_data = cur.fetchall()
        
        # Complaint type breakdown
        cur.execute(f"""
            SELECT ct.complaint_title_name, COUNT(bc.blotter_case_id) as case_count
            FROM complaint_title ct
            LEFT JOIN blotter_case bc ON bc.complaint_title_id = ct.complaint_title_id
            WHERE 1=1 {where_clause}
            GROUP BY ct.complaint_title_id, ct.complaint_title_name
            HAVING COUNT(bc.blotter_case_id) > 0
            ORDER BY case_count DESC
        """, params)
        complaint_data = cur.fetchall()
        
        cur.execute(f"SELECT COUNT(*) FROM blotter_case bc WHERE 1=1 {where_clause}", params)
        total_cases = cur.fetchone()[0]
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Header with logos
    logo_left = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    logo_right = os.path.join(settings.BASE_DIR, 'static', 'images', 'lupon-tagapamayapa.png')
    
    header_data = [[
        Image(logo_left, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_left) else '',
        Paragraph("Republic of the Philippines<br/>Office of the Barangay Captain<br/><b>BARANGAY SEÑOR SANTO NIÑO</b><br/>032 Legaspi Street, Cebu City<br/>Telephone No. (032) 254-9250/346-8802", 
                 ParagraphStyle('hdr', fontSize=11, alignment=TA_CENTER, leading=14)),
        Image(logo_right, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_right) else ''
    ]]
    header_table = Table(header_data, colWidths=[1*inch, 3.5*inch, 1*inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'RIGHT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'LEFT'), ('RIGHTPADDING', (0,0), (0,0), 0), ('LEFTPADDING', (2,0), (2,0), 0)]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Province/City/Month/Year info
    month_name = calendar.month_name[month] if month else "All Months"
    info_data = [[
        Paragraph(f"Province: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"For the Month of: <u>{month_name}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ], [
        Paragraph(f"City of: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"Calendar Year: <u>{year}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ]]
    info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
    info_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,-1), 10), ('RIGHTPADDING', (1,0), (1,-1), 10)]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))
    
    # Title
    elements.append(Paragraph("<b>TOTAL CASES BY STATUS REPORT</b>", ParagraphStyle('t', fontSize=14, alignment=TA_CENTER, spaceAfter=10)))
    elements.append(Spacer(1, 20))
    
    # Check if no cases
    if total_cases == 0:
        elements.append(Paragraph("<b>NO CASE FILED</b>", ParagraphStyle('nc', fontSize=16, alignment=TA_CENTER, textColor=colors.red)))
    else:
        # Case State Status
        elements.append(Paragraph("<b>CASE STATE BREAKDOWN</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
        elements.append(Spacer(1, 10))
        
        state_table_data = [['Case State', 'Number of Cases', 'Percentage']]
        for status, count in status_data:
            percentage = (count / total_cases * 100) if total_cases > 0 else 0
            state_table_data.append([status or 'Unknown', str(count), f"{percentage:.1f}%"])
        state_table_data.append(['TOTAL', str(total_cases), '100.0%'])
    
        state_table = Table(state_table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        state_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
            ('BACKGROUND', (0,1), (-1,-2), colors.beige),
            ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold')
        ]))
        elements.append(state_table)
        elements.append(Spacer(1, 25))
        
        # Settlement Status
        elements.append(Paragraph("<b>SETTLEMENT STATUS BREAKDOWN</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
        elements.append(Spacer(1, 10))
        
        settlement_table_data = [['Settlement Status', 'Number of Cases', 'Percentage']]
        settlement_total = sum(count for _, count in settlement_data)
        for status, count in settlement_data:
            percentage = (count / settlement_total * 100) if settlement_total > 0 else 0
            settlement_table_data.append([status or 'Unknown', str(count), f"{percentage:.1f}%"])
        
        settlement_table = Table(settlement_table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        settlement_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige)
        ]))
        elements.append(settlement_table)
        elements.append(Spacer(1, 25))
        
        # Complaint Type
        elements.append(Paragraph("<b>COMPLAINT TYPE BREAKDOWN</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
        elements.append(Spacer(1, 10))
        
        complaint_table_data = [['Complaint Type', 'Number of Cases', 'Percentage']]
        complaint_total = sum(count for _, count in complaint_data)
        for complaint_type, count in complaint_data:
            percentage = (count / complaint_total * 100) if complaint_total > 0 else 0
            complaint_table_data.append([complaint_type or 'Unknown', str(count), f"{percentage:.1f}%"])
        
        complaint_table = Table(complaint_table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        complaint_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 11),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige)
        ]))
        elements.append(complaint_table)
    
    doc.build(elements)
    buffer.seek(0)
    
    from datetime import datetime
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="total_cases_by_status_{datetime.now().strftime("%Y%m%d")}.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def case_summaries_report(request: HttpRequest):
    if request.method == "GET":
        auth = request.session.get("auth") or {}
        user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
        return render(request, "lupon_mem/case_summaries_filters.html", {
            'page_path': f'{user_role} / Reports / Case Summaries',
            'page_title': 'Case Summaries Report'
        })
    
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch
    from io import BytesIO
    import calendar, os
    
    month = _toi(request.POST.get('month'))
    year = _toi(request.POST.get('year'))
    where_conditions = []
    params = []
    
    if month and year:
        where_conditions.append("EXTRACT(MONTH FROM bc.date_filed) = %s")
        where_conditions.append("EXTRACT(YEAR FROM bc.date_filed) = %s")
        params.extend([month, year])
    elif year:
        where_conditions.append("EXTRACT(YEAR FROM bc.date_filed) = %s")
        params.append(year)
    
    where_clause = " AND " + " AND ".join(where_conditions) if where_conditions else ""
    
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT bc.blotter_case_num, bc.blotter_case_name,
                   STRING_AGG(DISTINCT UPPER(comp.last_name || ' ' || comp.first_name), ', ') as complainants,
                   STRING_AGG(DISTINCT UPPER(resp.last_name || ' ' || resp.first_name), ', ') as respondents,
                   bc.complaint_title_id, bc.settlement_status_id
            FROM blotter_case bc
            LEFT JOIN complainant_case cc ON cc.blotter_case_id = bc.blotter_case_id
            LEFT JOIN person comp ON comp.person_id = cc.person_id
            LEFT JOIN respondent_case rc ON rc.blotter_case_id = bc.blotter_case_id
            LEFT JOIN person resp ON resp.person_id = rc.person_id
            WHERE 1=1 {where_clause}
            GROUP BY bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name, bc.complaint_title_id, bc.settlement_status_id
            ORDER BY bc.blotter_case_num
        """, params)
        cases_data = cur.fetchall()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    elements = []
    
    # Header
    logo_left = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    logo_right = os.path.join(settings.BASE_DIR, 'static', 'images', 'lupon-tagapamayapa.png')
    
    header_data = [[
        Image(logo_left, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_left) else '',
        Paragraph("Republic of the Philippines<br/>Office of the Barangay Captain<br/><b>BARANGAY SEÑOR SANTO NIÑO</b><br/>032 Legaspi Street, Cebu City<br/>Telephone No. (032) 254-9250/346-8802", 
                 ParagraphStyle('hdr', fontSize=11, alignment=TA_CENTER, leading=14)),
        Image(logo_right, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_right) else ''
    ]]
    header_table = Table(header_data, colWidths=[1*inch, 3.5*inch, 1*inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'RIGHT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'LEFT'), ('RIGHTPADDING', (0,0), (0,0), 0), ('LEFTPADDING', (2,0), (2,0), 0)]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Province/City
    month_name = calendar.month_name[month] if month else "All Months"
    info_data = [[
        Paragraph(f"Province: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"For the Month of: <u>{month_name}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ], [
        Paragraph(f"City of: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"Calendar Year: <u>{year}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ]]
    info_table = Table(info_data, colWidths=[3.5*inch, 5.5*inch])
    elements.append(info_table)
    elements.append(Spacer(1, 15))
    
    # Title
    elements.append(Paragraph("<b>LUPONG TAGAPAMAYAPA REPORT: Cases Filed / Action Taken and Problems Encountered on KP Implementation</b>", 
                             ParagraphStyle('t', fontSize=11, alignment=TA_CENTER)))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("<b>PART I. NATURE OF CASES AND ACTIONS TAKEN</b>", 
                             ParagraphStyle('st', fontSize=10, alignment=TA_CENTER)))
    elements.append(Spacer(1, 10))
    
    # Table
    h = ParagraphStyle('h', fontSize=6.5, alignment=TA_CENTER, leading=7)
    h2 = ParagraphStyle('h2', fontSize=5.5, alignment=TA_CENTER, leading=6.5, splitLongWords=False)
    c = ParagraphStyle('c', fontSize=7, leading=9)
    
    table_data = [[
        Paragraph('<b>CASE NO.<br/>(1)</b>', h),
        Paragraph('<b>CASE TITLE<br/>(2)</b>', h),
        Paragraph('<b>COMPLAINANT\'S VS<br/>RESPONDENTS<br/>(3)</b>', h),
        Paragraph('<b>NATURE OF CASE<br/>(4)</b>', h), '', '',
        Paragraph('<b>ACTIONS TAKEN<br/>(5)</b>', h), '', '', '', '', '', '',
        Paragraph('<b>REMARKS<br/>(5h)</b>', h)
    ], [
        '', '', '',
        Paragraph('<b>CRIMINAL<br/>(4a)</b>', h2),
        Paragraph('<b>CIVIL<br/>(4b)</b>', h2),
        Paragraph('<b>OTHERS<br/>(4c)</b>', h2),
        Paragraph('<b>MEDIATED<br/>(5a)</b>', h2),
        Paragraph('<b>CONCILIATED<br/>(5b)</b>', h2),
        Paragraph('<b>ARBITRATED<br/>(5c)</b>', h2),
        Paragraph('<b>REPUDIATED<br/>(5d)</b>', h2),
        Paragraph('<b>DISMISSED<br/>(5e)</b>', h2),
        Paragraph('<b>CERTIFIED<br/>(5f)</b>', h2),
        Paragraph('<b>PENDING<br/>(5g)</b>', h2),
        ''
    ]]
    
    cell_data = ParagraphStyle('cd', fontSize=6, leading=8)
    check_style = ParagraphStyle('chk', fontSize=8, alignment=TA_CENTER)
    
    for case in cases_data:
        complaint_title_id = case[4]
        settlement_status_id = case[5]
        
        criminal = Paragraph('✓', check_style) if complaint_title_id == 2 else ''
        civil = Paragraph('✓', check_style) if complaint_title_id == 1 else ''
        
        mediated = Paragraph('✓', check_style) if settlement_status_id == 15 else ''
        conciliated = Paragraph('✓', check_style) if settlement_status_id == 16 else ''
        arbitrated = Paragraph('✓', check_style) if settlement_status_id == 8 else ''
        repudiated = Paragraph('✓', check_style) if settlement_status_id == 9 else ''
        dismissed = Paragraph('✓', check_style) if settlement_status_id in (10, 11, 12) else ''
        certified = Paragraph('✓', check_style) if settlement_status_id == 5 else ''
        pending = Paragraph('✓', check_style) if settlement_status_id == 1 else ''
        
        table_data.append([
            Paragraph(f"BC# {case[0]}" if case[0] else '', cell_data),
            Paragraph((case[1] or '').upper(), c),
            Paragraph(f"{case[2] or ''} vs {case[3] or ''}", c),
            criminal, civil, '', mediated, conciliated, arbitrated, repudiated, dismissed, certified, pending, ''
        ])
    
    t = Table(table_data, colWidths=[0.85*inch, 1.3*inch, 1.7*inch, 0.45*inch, 0.4*inch, 0.45*inch, 0.55*inch, 0.65*inch, 0.65*inch, 0.65*inch, 0.6*inch, 0.6*inch, 0.55*inch, 0.85*inch])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,1), colors.lightgrey),
        ('SPAN', (0,0), (0,1)),
        ('SPAN', (1,0), (1,1)),
        ('SPAN', (2,0), (2,1)),
        ('SPAN', (3,0), (5,0)),
        ('SPAN', (6,0), (12,0)),
        ('SPAN', (13,0), (13,1)),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,1), 'Helvetica-Bold')
    ]))
    elements.append(t)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    month_str = f"{month:02d}" if month else "00"
    response['Content-Disposition'] = f'attachment; filename="lupong_tagapamayapa_report_{year}_{month_str}%20({month_name[:3].upper() if month else "ALL"}).pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def settlement_statistics_report(request: HttpRequest):
    """Generate PDF report of settlement statistics"""
    from django.http import HttpResponse
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from io import BytesIO
    
    # Get settlement statistics
    with connection.cursor() as cur:
        # Settlement status breakdown
        cur.execute("""
            SELECT 
                COALESCE(ss.settlement_status_name, 'Unknown') as status,
                COUNT(bc.blotter_case_id) as case_count
            FROM settlement_status ss
            LEFT JOIN blotter_case bc ON bc.settlement_status_id = ss.settlement_status_id
            GROUP BY ss.settlement_status_id, ss.settlement_status_name
            ORDER BY case_count DESC
        """)
        settlement_data = cur.fetchall()
        
        # Mediation success rate
        cur.execute("""
            SELECT 
                COUNT(CASE WHEN UPPER(ss.settlement_status_name) = 'SETTLED' THEN 1 END) as settled_cases,
                COUNT(CASE WHEN UPPER(ss.settlement_status_name) = 'NOT SETTLED' THEN 1 END) as not_settled_cases,
                COUNT(bc.blotter_case_id) as total_cases
            FROM blotter_case bc
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
        """)
        mediation_stats = cur.fetchone()
        
        # Cases by complaint type
        cur.execute("""
            SELECT 
                COALESCE(ct.complaint_title_name, 'Unknown') as complaint_type,
                COUNT(bc.blotter_case_id) as case_count,
                COUNT(CASE WHEN UPPER(ss.settlement_status_name) = 'SETTLED' THEN 1 END) as settled_count
            FROM complaint_title ct
            LEFT JOIN blotter_case bc ON bc.complaint_title_id = ct.complaint_title_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            GROUP BY ct.complaint_title_id, ct.complaint_title_name
            HAVING COUNT(bc.blotter_case_id) > 0
            ORDER BY case_count DESC
            LIMIT 10
        """)
        complaint_type_data = cur.fetchall()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Add professional header
    add_barangay_header(elements, styles, "SETTLEMENT STATISTICS REPORT")
    
    # Settlement Status Breakdown
    elements.append(Paragraph("Settlement Status Breakdown", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    settlement_table_data = [['Settlement Status', 'Number of Cases', 'Percentage']]
    total_settlement_cases = sum(count for _, count in settlement_data)
    
    for status, count in settlement_data:
        percentage = (count / total_settlement_cases * 100) if total_settlement_cases > 0 else 0
        settlement_table_data.append([status, str(count), f"{percentage:.1f}%"])
    
    settlement_table = Table(settlement_table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
    settlement_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(settlement_table)
    elements.append(Spacer(1, 30))
    
    # Mediation Success Rate
    elements.append(Paragraph("Mediation Success Rate", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    settled_cases, not_settled_cases, total_cases = mediation_stats
    success_rate = (settled_cases / total_cases * 100) if total_cases > 0 else 0
    
    success_data = [
        ['Total Cases Processed', str(total_cases)],
        ['Successfully Settled', str(settled_cases)],
        ['Not Settled', str(not_settled_cases)],
        ['Success Rate', f"{success_rate:.1f}%"]
    ]
    
    success_table = Table(success_data, colWidths=[3*inch, 2*inch])
    success_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgreen),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(success_table)
    elements.append(Spacer(1, 30))
    
    # Top Complaint Types
    elements.append(Paragraph("Top Complaint Types by Settlement Rate", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    complaint_table_data = [['Complaint Type', 'Total Cases', 'Settled', 'Settlement Rate']]
    
    for complaint_type, total_count, settled_count in complaint_type_data:
        settlement_rate = (settled_count / total_count * 100) if total_count > 0 else 0
        complaint_table_data.append([
            complaint_type[:30] + '...' if len(complaint_type) > 30 else complaint_type,
            str(total_count),
            str(settled_count),
            f"{settlement_rate:.1f}%"
        ])
    
    complaint_table = Table(complaint_table_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1.5*inch])
    complaint_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(complaint_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    from datetime import datetime
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="settlement_statistics_{datetime.now().strftime("%Y%m%d")}.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def monthly_activity_report(request: HttpRequest):
    """Generate PDF report of monthly lupon activities"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch
    from io import BytesIO
    from datetime import datetime, timedelta
    import calendar, os
    
    month = _toi(request.POST.get('month')) if request.method == 'POST' else datetime.now().month
    year = _toi(request.POST.get('year')) if request.method == 'POST' else datetime.now().year
    
    # Get month data
    current_month = datetime(year, month, 1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)
    
    with connection.cursor() as cur:
        # Cases filed this month
        cur.execute("""
            SELECT COUNT(*) as cases_filed
            FROM blotter_case bc
            WHERE bc.date_filed >= %s AND bc.date_filed < %s
        """, [current_month, next_month])
        cases_filed = cur.fetchone()[0]
        
        # Cases settled this month
        cur.execute("""
            SELECT COUNT(*) as cases_settled
            FROM blotter_case bc
            JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE UPPER(ss.settlement_status_name) = 'SETTLED'
            AND bc.date_filed >= %s AND bc.date_filed < %s
        """, [current_month, next_month])
        cases_settled = cur.fetchone()[0]
        
        # Hearings conducted this month
        cur.execute("""
            SELECT COUNT(*) as hearings_conducted
            FROM case_progress_tracking cpt
            JOIN case_progress_type cpt_type ON cpt_type.case_progress_type_id = cpt.case_progress_type_id
            WHERE UPPER(cpt_type.case_progress_type_name) IN ('HEARING HELD', 'CONCILIATION HELD')
            AND cpt.date_processed >= %s AND cpt.date_processed < %s
        """, [current_month, next_month])
        hearings_conducted = cur.fetchone()[0]
        
        # Forms processed this month
        cur.execute("""
            SELECT 
                kf.form_code,
                COUNT(*) as form_count
            FROM blotter_kp_submission bks
            JOIN kp_form kf ON kf.form_id = bks.form_id
            WHERE bks.submitted_at >= %s AND bks.submitted_at < %s
            AND UPPER(bks.status) = 'SUBMITTED'
            GROUP BY kf.form_id, kf.form_code
            ORDER BY form_count DESC
            LIMIT 10
        """, [current_month, next_month])
        forms_data = cur.fetchall()
        
        # Daily activity breakdown
        cur.execute("""
            SELECT 
                DATE(bc.date_filed) as activity_date,
                COUNT(*) as cases_count
            FROM blotter_case bc
            WHERE bc.date_filed >= %s AND bc.date_filed < %s
            GROUP BY DATE(bc.date_filed)
            ORDER BY activity_date
        """, [current_month, next_month])
        daily_activity = cur.fetchall()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Header with logos
    logo_left = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    logo_right = os.path.join(settings.BASE_DIR, 'static', 'images', 'lupon-tagapamayapa.png')
    
    header_data = [[
        Image(logo_left, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_left) else '',
        Paragraph("Republic of the Philippines<br/>Office of the Barangay Captain<br/><b>BARANGAY SEÑOR SANTO NIÑO</b><br/>032 Legaspi Street, Cebu City<br/>Telephone No. (032) 254-9250/346-8802", 
                 ParagraphStyle('hdr', fontSize=11, alignment=TA_CENTER, leading=14)),
        Image(logo_right, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_right) else ''
    ]]
    header_table = Table(header_data, colWidths=[1*inch, 3.5*inch, 1*inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'RIGHT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'LEFT'), ('RIGHTPADDING', (0,0), (0,0), 0), ('LEFTPADDING', (2,0), (2,0), 0)]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Province/City/Month/Year info
    month_name = calendar.month_name[month]
    info_data = [[
        Paragraph(f"Province: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"For the Month of: <u>{month_name}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ], [
        Paragraph(f"City of: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"Calendar Year: <u>{year}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ]]
    info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
    info_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,-1), 10), ('RIGHTPADDING', (1,0), (1,-1), 10)]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))
    
    # Title
    elements.append(Paragraph(f"<b>MONTHLY ACTIVITY REPORT - {current_month.strftime('%B %Y')}</b>", ParagraphStyle('t', fontSize=14, alignment=TA_CENTER, spaceAfter=10)))
    elements.append(Spacer(1, 20))
    
    # Monthly Summary
    elements.append(Paragraph("<b>MONTHLY SUMMARY</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
    elements.append(Spacer(1, 10))
    
    summary_data = [
        ['Activity', 'Count'],
        ['Cases Filed', str(cases_filed)],
        ['Cases Settled', str(cases_settled)],
        ['Hearings Conducted', str(hearings_conducted)],
        ['Total Forms Processed', str(sum(count for _, count in forms_data))]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige)
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 30))
    
    # Daily Activity Breakdown
    if daily_activity:
        elements.append(Paragraph("<b>DAILY ACTIVITY BREAKDOWN</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
        elements.append(Spacer(1, 10))
        
        daily_table_data = [['Date', 'Cases Filed']]
        for activity_date, cases_count in daily_activity:
            daily_table_data.append([activity_date.strftime('%B %d, %Y'), str(cases_count)])
        
        daily_table = Table(daily_table_data, colWidths=[3*inch, 2*inch])
        daily_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige)
        ]))
        
        elements.append(daily_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_activity_{current_month.strftime("%Y_%m")}.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def case_timeline_pdf(request: HttpRequest, case_id: int):
    """Generate PDF report of case timeline"""
    from django.http import HttpResponse
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from io import BytesIO
    
    # Get case timeline data
    with connection.cursor() as cur:
        # Get case basic info
        cur.execute("""
            SELECT bc.blotter_case_num, bc.blotter_case_name, bc.date_filed,
                   COALESCE(ct.complaint_title_name, '') AS complaint_title,
                   COALESCE(cn.case_name, '') AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_info = cur.fetchone()
        if not case_info:
            return HttpResponse("Case not found", status=404)
        
        # Get timeline events
        cur.execute("""
            SELECT 
                cpt.date_processed,
                cpt_type.case_progress_type_name,
                cpt.remarks,
                COALESCE(p.first_name || ' ' || p.last_name, 'System') as processed_by
            FROM case_progress_tracking cpt
            JOIN case_progress_type cpt_type ON cpt_type.case_progress_type_id = cpt.case_progress_type_id
            LEFT JOIN staff s ON s.staff_id = cpt.processed_by
            LEFT JOIN person p ON p.person_id = s.person_id
            WHERE cpt.blotter_case_id = %s
            ORDER BY cpt.date_processed ASC
        """, [case_id])
        timeline_events = cur.fetchall()
        
        # Get forms submitted
        cur.execute("""
            SELECT 
                kf.form_code,
                kf.form_name,
                bks.submitted_at,
                bks.status,
                bks.processed_by_name
            FROM blotter_kp_submission bks
            JOIN kp_form kf ON kf.form_id = bks.form_id
            WHERE bks.blotter_case_id = %s
            ORDER BY bks.submitted_at ASC
        """, [case_id])
        forms_data = cur.fetchall()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Add professional header
    add_barangay_header(elements, styles, f"CASE TIMELINE REPORT - {case_info[0]}")
    
    # Case Information
    case_info_style = ParagraphStyle(
        'CaseInfo',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10
    )
    elements.append(Paragraph(f"<b>Case Name:</b> {case_info[1] or 'Untitled'}", case_info_style))
    elements.append(Paragraph(f"<b>Date Filed:</b> {case_info[2].strftime('%B %d, %Y') if case_info[2] else 'N/A'}", case_info_style))
    elements.append(Paragraph(f"<b>Complaint Type:</b> {case_info[3] or 'N/A'}", case_info_style))
    elements.append(Paragraph(f"<b>Case Nature:</b> {case_info[4] or 'N/A'}", case_info_style))
    elements.append(Spacer(1, 20))
    
    # Timeline Events
    if timeline_events:
        elements.append(Paragraph("Timeline of Events", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        timeline_data = [['Date', 'Event', 'Processed By', 'Remarks']]
        for event in timeline_events:
            timeline_data.append([
                event[0].strftime('%m/%d/%Y %I:%M %p') if event[0] else 'N/A',
                event[1] or 'N/A',
                event[3] or 'N/A',
                (event[2] or 'N/A')[:50] + '...' if event[2] and len(event[2]) > 50 else (event[2] or 'N/A')
            ])
        
        timeline_table = Table(timeline_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
        timeline_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        
        elements.append(timeline_table)
        elements.append(Spacer(1, 30))
    
    # Forms Submitted
    if forms_data:
        elements.append(Paragraph("Forms Submitted", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        forms_table_data = [['Form Code', 'Form Name', 'Submitted', 'Status', 'Processed By']]
        for form in forms_data:
            forms_table_data.append([
                form[0] or 'N/A',
                (form[1] or 'N/A')[:30] + '...' if form[1] and len(form[1]) > 30 else (form[1] or 'N/A'),
                form[2].strftime('%m/%d/%Y') if form[2] else 'N/A',
                form[3] or 'N/A',
                form[4] or 'N/A'
            ])
        
        forms_table = Table(forms_table_data, colWidths=[1*inch, 2.5*inch, 1*inch, 1*inch, 1.5*inch])
        forms_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        
        elements.append(forms_table)
    
    # Date generated
    from datetime import datetime
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=1
    )
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", date_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="case_{case_info[0]}_timeline.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def case_forms_pdf(request: HttpRequest, case_id: int):
    """Generate PDF report of all forms for a case"""
    from django.http import HttpResponse
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from io import BytesIO
    
    # Get case and forms data
    with connection.cursor() as cur:
        # Get case basic info
        cur.execute("""
            SELECT bc.blotter_case_num, bc.blotter_case_name
            FROM blotter_case bc
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_info = cur.fetchone()
        if not case_info:
            return HttpResponse("Case not found", status=404)
        
        # Get detailed forms information
        cur.execute("""
            SELECT 
                kf.form_code,
                kf.form_name,
                bks.submitted_at,
                bks.processed_at,
                bks.status,
                bks.processed_by_name,
                bks.processed_by_position
            FROM blotter_kp_submission bks
            JOIN kp_form kf ON kf.form_id = bks.form_id
            WHERE bks.blotter_case_id = %s
            ORDER BY bks.submitted_at ASC
        """, [case_id])
        forms_data = cur.fetchall()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Add professional header
    add_barangay_header(elements, styles, f"FORMS REPORT - CASE {case_info[0]}")
    
    # Case Information
    case_info_style = ParagraphStyle(
        'CaseInfo',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=20
    )
    elements.append(Paragraph(f"<b>Case Name:</b> {case_info[1] or 'Untitled'}", case_info_style))
    elements.append(Paragraph(f"<b>Total Forms:</b> {len(forms_data)}", case_info_style))
    elements.append(Spacer(1, 20))
    
    # Forms Table
    if forms_data:
        forms_table_data = [[
            'Form Code', 'Form Name', 'Submitted', 'Processed', 'Status', 'Processed By'
        ]]
        
        for form in forms_data:
            forms_table_data.append([
                form[0] or 'N/A',
                (form[1] or 'N/A')[:40] + '...' if form[1] and len(form[1]) > 40 else (form[1] or 'N/A'),
                form[2].strftime('%m/%d/%Y %I:%M %p') if form[2] else 'N/A',
                form[3].strftime('%m/%d/%Y %I:%M %p') if form[3] else 'N/A',
                form[4] or 'N/A',
                f"{form[5] or 'N/A'}\n{form[6] or ''}" if form[5] else 'N/A'
            ])
        
        forms_table = Table(forms_table_data, colWidths=[0.8*inch, 2*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1*inch])
        forms_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        
        elements.append(forms_table)
    else:
        elements.append(Paragraph("No forms have been submitted for this case.", styles['Normal']))
    
    # Date generated
    from datetime import datetime
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=1
    )
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", date_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="case_{case_info[0]}_forms.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def case_hearings_pdf(request: HttpRequest, case_id: int):
    """Generate PDF report of all hearings for a case"""
    from django.http import HttpResponse
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from io import BytesIO
    
    # Get case and hearings data
    with connection.cursor() as cur:
        # Get case basic info
        cur.execute("""
            SELECT bc.blotter_case_num, bc.blotter_case_name
            FROM blotter_case bc
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_info = cur.fetchone()
        if not case_info:
            return HttpResponse("Case not found", status=404)
        
        # Get hearings data using the function
        cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
        cols = [c[0] for c in cur.description] if cur.description else []
        hearings_data = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Add professional header
    add_barangay_header(elements, styles, f"HEARINGS REPORT - CASE {case_info[0]}")
    
    # Case Information
    case_info_style = ParagraphStyle(
        'CaseInfo',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=20
    )
    elements.append(Paragraph(f"<b>Case Name:</b> {case_info[1] or 'Untitled'}", case_info_style))
    elements.append(Paragraph(f"<b>Total Hearings:</b> {len(hearings_data)}", case_info_style))
    elements.append(Spacer(1, 20))
    
    # Hearings Table
    if hearings_data:
        hearings_table_data = [[
            'Source', 'Hearing Date', 'Hearing Time', 'Status', 'Outcome', 'Attendance'
        ]]
        
        for hearing in hearings_data:
            attendance_info = []
            if hearing.get('complainant_attended') == 'TRUE':
                attendance_info.append('Complainant')
            if hearing.get('respondent_attended') == 'TRUE':
                attendance_info.append('Respondent')
            
            hearings_table_data.append([
                hearing.get('source', 'N/A'),
                hearing.get('hearing_date', 'N/A'),
                hearing.get('hearing_time', 'N/A'),
                'HELD' if hearing.get('hearing_held') else 'NOT HELD',
                hearing.get('settlement_outcome', 'N/A'),
                ', '.join(attendance_info) if attendance_info else 'None'
            ])
        
        hearings_table = Table(hearings_table_data, colWidths=[1*inch, 1.2*inch, 1*inch, 1*inch, 1.3*inch, 1.5*inch])
        hearings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        
        elements.append(hearings_table)
    else:
        elements.append(Paragraph("No hearings have been scheduled for this case.", styles['Normal']))
    
    # Date generated
    from datetime import datetime
    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=1
    )
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", date_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="case_{case_info[0]}_hearings.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def blotter_reports_summary(request: HttpRequest):
    """Generate PDF report of blotter reports summary"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.units import inch
    from io import BytesIO
    from datetime import datetime as dt
    import calendar, os
    
    month = _toi(request.POST.get('month')) if request.method == 'POST' else dt.now().month
    year = _toi(request.POST.get('year')) if request.method == 'POST' else dt.now().year
    
    # Use get_all_report_details() to avoid duplicates
    with connection.cursor() as cur:
        cur.execute("""
            SELECT * FROM get_all_report_details() 
            WHERE EXTRACT(MONTH FROM date_time_reported::timestamp) = %s 
            AND EXTRACT(YEAR FROM date_time_reported::timestamp) = %s
            ORDER BY blotter_report_id DESC LIMIT 100
        """, [month, year])
        columns = [col[0] for col in cur.description]
        reports_data = [dict(zip(columns, row)) for row in cur.fetchall()]
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Header with logos
    logo_left = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    logo_right = os.path.join(settings.BASE_DIR, 'static', 'images', 'lupon-tagapamayapa.png')
    
    header_data = [[
        Image(logo_left, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_left) else '',
        Paragraph("Republic of the Philippines<br/>Office of the Barangay Captain<br/><b>BARANGAY SEÑOR SANTO NIÑO</b><br/>032 Legaspi Street, Cebu City<br/>Telephone No. (032) 254-9250/346-8802", 
                 ParagraphStyle('hdr', fontSize=11, alignment=TA_CENTER, leading=14)),
        Image(logo_right, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_right) else ''
    ]]
    header_table = Table(header_data, colWidths=[1*inch, 3.5*inch, 1*inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'RIGHT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'LEFT'), ('RIGHTPADDING', (0,0), (0,0), 0), ('LEFTPADDING', (2,0), (2,0), 0)]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Province/City/Month/Year info
    month_name = calendar.month_name[month] if month else "All Months"
    info_data = [[
        Paragraph(f"Province: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"For the Month of: <u>{month_name}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ], [
        Paragraph(f"City of: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"Calendar Year: <u>{year}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ]]
    info_table = Table(info_data, colWidths=[3.5*inch, 4*inch])
    info_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,-1), 10), ('RIGHTPADDING', (1,0), (1,-1), 10)]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))
    
    # Title
    elements.append(Paragraph("<b>BLOTTER REPORTS SUMMARY</b>", ParagraphStyle('t', fontSize=14, alignment=TA_CENTER, spaceAfter=10)))
    elements.append(Spacer(1, 20))
    
    # Check if no reports
    total_reports = len(reports_data)
    if total_reports == 0:
        elements.append(Paragraph("<b>NO BLOTTER REPORT FILED</b>", ParagraphStyle('nc', fontSize=16, alignment=TA_CENTER, textColor=colors.red)))
        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="blotter_reports_summary_{dt.now().strftime("%Y%m%d")}.pdf"'
        return response
    
    # Summary statistics
    paid_count = sum(1 for r in reports_data if r.get('payment_status_name') == 'PAID')
    unpaid_count = sum(1 for r in reports_data if r.get('payment_status_name') == 'UNPAID')
    with_case = sum(1 for r in reports_data if r.get('has_case'))
    
    elements.append(Paragraph("<b>SUMMARY STATISTICS</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
    elements.append(Spacer(1, 10))
    
    summary_data = [
        ['Total Reports', str(total_reports)],
        ['With Case Filed', str(with_case)],
        ['Paid', str(paid_count)],
        ['Unpaid', str(unpaid_count)]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,-1), colors.beige),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,-1), 10)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Reports table
    elements.append(Paragraph("<b>DETAILED REPORTS</b>", ParagraphStyle('st', fontSize=12, alignment=TA_CENTER)))
    elements.append(Spacer(1, 10))
    
    # Cell style for wrapping text
    cell_style = ParagraphStyle('cell', fontSize=7, leading=8, alignment=TA_CENTER)
    
    table_data = [[
        Paragraph('<b>ID</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER)),
        Paragraph('<b>Subject</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER)),
        Paragraph('<b>Complainant</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER)),
        Paragraph('<b>Respondent</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER)),
        Paragraph('<b>Status</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER)),
        Paragraph('<b>Payment</b>', ParagraphStyle('hdr', fontSize=8, alignment=TA_CENTER))
    ]]
    
    for report in reports_data:
        table_data.append([
            Paragraph(str(report.get('blotter_report_id')), cell_style),
            Paragraph(report.get('incident_subject') or 'No Subject', cell_style),
            Paragraph(report.get('complainant_names') or 'N/A', cell_style),
            Paragraph(report.get('respondent_names') or 'N/A', cell_style),
            Paragraph(report.get('current_status_name') or 'N/A', cell_style),
            Paragraph(report.get('payment_status_name') or 'N/A', cell_style)
        ])
    
    table = Table(table_data, colWidths=[0.5*inch, 1.8*inch, 1.5*inch, 1.5*inch, 1.2*inch, 0.8*inch])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige)
    ]))
    
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="blotter_reports_summary_{dt.now().strftime("%Y%m%d")}.pdf"'
    return response


@session_login_required
@role_required(*LUPON_ROLES)
def incident_by_location_report(request: HttpRequest):
    """Generate PDF report of incidents by location"""
    from django.http import HttpResponse
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    import os
    
    # Get filters if POST
    where_conditions = []
    params = []
    if request.method == "POST":
        date_from = request.POST.get('date_from')
        date_to = request.POST.get('date_to')
        if date_from:
            where_conditions.append("br.date_time_reported >= %s")
            params.append(date_from)
        if date_to:
            where_conditions.append("br.date_time_reported <= %s")
            params.append(date_to)
    
    where_clause = " AND " + " AND ".join(where_conditions) if where_conditions else ""
    
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT 
                COALESCE(a.street, 'Unknown Street') as street,
                COALESCE(a.barangay, 'Unknown Barangay') as barangay,
                COUNT(br.blotter_report_id) as incident_count,
                COUNT(CASE WHEN bc.blotter_case_id IS NOT NULL AND UPPER(ss.settlement_status_name) = 'SETTLED' THEN 1 END) as settled_count
            FROM blotter_report br
            LEFT JOIN addresss a ON a.address_id = br.incident_address_id
            LEFT JOIN blotter_case bc ON bc.blotter_report_id = br.blotter_report_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE 1=1 {where_clause}
            GROUP BY a.street, a.barangay
            ORDER BY incident_count DESC, a.street
        """, params)
        location_data = cur.fetchall()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Header with logos
    logo_left = os.path.join(settings.BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
    logo_right = os.path.join(settings.BASE_DIR, 'static', 'images', 'lupon-tagapamayapa.png')
    
    header_data = [[
        Image(logo_left, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_left) else '',
        Paragraph("Republic of the Philippines<br/>Office of the Barangay Captain<br/><b>BARANGAY SEÑOR SANTO NIÑO</b><br/>032 Legaspi Street, Cebu City<br/>Telephone No. (032) 254-9250/346-8802", 
                 ParagraphStyle('hdr', fontSize=11, alignment=TA_CENTER, leading=14)),
        Image(logo_right, width=0.9*inch, height=0.9*inch) if os.path.exists(logo_right) else ''
    ]]
    header_table = Table(header_data, colWidths=[1*inch, 3.5*inch, 1*inch])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (0,0), 'RIGHT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'LEFT'), ('RIGHTPADDING', (0,0), (0,0), 0), ('LEFTPADDING', (2,0), (2,0), 0)]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))
    
    # Province/City info
    from datetime import datetime
    import calendar
    current_date = datetime.now()
    month_name = calendar.month_name[current_date.month]
    info_data = [[
        Paragraph(f"Province: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"For the Month of: <u>{month_name}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ], [
        Paragraph(f"City of: <u>CEBU</u>", ParagraphStyle('i', fontSize=10)),
        Paragraph(f"Calendar Year: <u>{current_date.year}</u>", ParagraphStyle('i', fontSize=10, alignment=2))
    ]]
    info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
    info_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,-1), 10), ('RIGHTPADDING', (1,0), (1,-1), 10)]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))
    
    # Title
    elements.append(Paragraph("<b>INCIDENT REPORTS BY LOCATION</b>", ParagraphStyle('t', fontSize=14, alignment=TA_CENTER, spaceAfter=10)))
    elements.append(Spacer(1, 20))
    
    table_data = [['Street', 'Barangay', 'Incidents', 'Settled', 'Rate']]
    total_incidents = sum(row[2] for row in location_data)
    total_settled = sum(row[3] for row in location_data)
    
    for street, barangay, incident_count, settled_count in location_data:
        settlement_rate = (settled_count / incident_count * 100) if incident_count > 0 else 0
        table_data.append([
            street,
            barangay,
            str(incident_count),
            str(settled_count),
            f"{settlement_rate:.0f}%"
        ])
    
    # Add total row
    overall_rate = (total_settled / total_incidents * 100) if total_incidents > 0 else 0
    table_data.append(['TOTAL', '', str(total_incidents), str(total_settled), f"{overall_rate:.0f}%"])
    
    table = Table(table_data, colWidths=[2*inch, 2*inch, 1*inch, 1*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    
    from datetime import datetime
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="incident_by_location_{datetime.now().strftime("%Y%m%d")}.pdf"'
    return response