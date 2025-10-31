# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid

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
    q_raw        = (request.GET.get("q") or "").strip()
    f_payment    = (request.GET.get("payment") or "").strip()            # '', PAID, UNPAID, DECLINED
    f_blotter    = (request.GET.get("blotter_status") or "").strip()     # '', FOR LUPON REVIEW, REVIEWED
    f_date_from  = (request.GET.get("date_from") or "").strip()
    f_date_to    = (request.GET.get("date_to") or "").strip()

    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip()

    # ✅ Payment filter now includes DECLINED
    payment_options = ["", "PAID", "UNPAID", "DECLINED"]
    blotter_options = ["", "FOR LUPON REVIEW", "REVIEWED"]

    with connection.cursor() as cur:
        sql = """
        WITH base AS (
          SELECT
            br.blotter_report_id                               AS id,
            COALESCE(br.incident_subject,'(no subject)')       AS subject,
            to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
            br.date_time_reported                               AS reported_sort,
            ps.payment_status_name                              AS payment_status,
            CASE
              WHEN ps.payment_status_name IS NULL OR ps.payment_status_name = '' THEN 'FOR LUPON REVIEW'
              WHEN UPPER(ps.payment_status_name) IN ('PAID','UNPAID','DECLINED') THEN 'REVIEWED'
              ELSE NULL
            END                                                 AS blotter_status
          FROM blotter_report br
          LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
        )
        SELECT id, subject, reported_at, payment_status, blotter_status
        FROM base
        WHERE 1=1
        """
        params = []

        if q_raw:
            sql += " AND subject ILIKE CONCAT('%%', %s, '%%')"
            params.append(q_raw)

        # ✅ Allow PAID / UNPAID / DECLINED filters
        if f_payment and f_payment.upper() in ("PAID", "UNPAID", "DECLINED"):
            sql += " AND UPPER(payment_status) = UPPER(%s)"
            params.append(f_payment)

        if f_blotter:
            sql += " AND blotter_status = %s"
            params.append(f_blotter)

        if f_date_from:
            sql += " AND reported_sort::date >= %s"
            params.append(f_date_from)
        if f_date_to:
            sql += " AND reported_sort::date <= %s"
            params.append(f_date_to)

        sql += " ORDER BY reported_sort DESC LIMIT 500"
        cur.execute(sql, params)
        rows = cur.fetchall()

    return render(
        request,
        "lupon_mem/report_list.html",
        {
            "rows": rows,
            "q": q_raw,
            "user_role": user_role,
            "LUPON_ROLES_LIST": LUPON_ROLES_LIST,
            "payment_options": payment_options,
            "blotter_options": blotter_options,
            "f_payment": f_payment,
            "f_blotter": f_blotter,
            "f_date_from": f_date_from,
            "f_date_to": f_date_to,
        },
    )





@session_login_required
@role_required(*LUPON_ROLES)
def report_new(request: HttpRequest):
    if request.method == "GET":
        return render(request, "lupon_mem/report_new.html", {"page_title": "New Report"})

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

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
            SELECT create_blotter_report(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            [
                staff_id,
                request.POST.get("incident_subject") or None,
                request.POST.get("incident_desc") or None,
                request.POST.get("incident_date") or None,
                request.POST.get("incident_time") or None,
                incident_address_id,  # <— now filled if we created one
                complainant_id,
                respondent_ids if respondent_ids else None,
                None,  # evidence jsonb
            ],
        )
        report_id = cur.fetchone()[0]

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
            "page_title": "Confirm & Open Case",
            "user_role": user_role,
            "initial_case_name": initial_case_name,
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
                   to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
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
                   a.longitude
            FROM blotter_report br
            LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
            LEFT JOIN addresss a        ON a.address_id = br.incident_address_id
            LEFT JOIN purok_sitio pks   ON pks.purok_sitio_id = a.purok_sitio_id
            WHERE br.blotter_report_id=%s
        """, [report_id])
        rpt = cur.fetchone()
        if not rpt:
            return HttpResponseBadRequest("Report not found.")

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

        # picklist data
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
        case_natures = cur.fetchall()
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
        settlements = cur.fetchall()

        # latest review trail entry (who/when/remarks)
        # Note: adjust table/column names if they differ in your schema.
        cur.execute("""
            SELECT
              rs.report_status_name      AS action,             -- APPROVED / DECLINED / REVIEWED ...
              rsd.remarks                AS remarks,            -- reason text (if any)
              to_char(rsd.verification_date,'YYYY-MM-DD HH24:MI') AS acted_at,
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

    pay_status = (rpt[4] or "—").upper()
    # is reviewed if payment status is conclusive OR we have an approve/decline entry
    action = (latest_review[0] if latest_review else "") or ""
    is_reviewed = pay_status in ("PAID", "UNPAID", "DECLINED") or action in ("APPROVED", "DECLINED")

    ctx = {
        "page_title": "Approve Blotter Report",
        "report": rpt,
        "parties": parties,
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlements,
        "user_role": role,
        "LUPON_ROLES_LIST": LUPON_ROLES_LIST,

        # review meta (safe-guard for None)
        "is_reviewed": is_reviewed,
        "review_action": action,
        "reviewed_by": (latest_review[4] if latest_review else None),
        "reviewed_at": (latest_review[2] if latest_review else None),
        "review_remarks": (latest_review[1] if latest_review else None),
    }
    return render(request, "lupon_mem/report_review.html", ctx)


# APPROVE (Lupon -> set UNPAID via DB func)
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def report_approve(request: HttpRequest, report_id: int):
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        return HttpResponseBadRequest("Missing staff id.")

    # DEBUG: show who/what is approving
    print("\n[DEBUG][APPROVE] report_id=", report_id, " staff_id=", staff_id)
    try:
        with connection.cursor() as cur:
            print("[DEBUG][APPROVE] SQL → approve_report_set_unpaid(%s,%s,%s)")
            cur.execute(
                "SELECT approve_report_set_unpaid(%s,%s,%s)",
                [report_id, staff_id, "Approved for case payment"],
            )
            res = cur.fetchone()
            print("[DEBUG][APPROVE] DB result:", res)
    except Exception as e:
        print("[DEBUG][APPROVE][ERROR]", e)
        raise

    messages.success(request, f"Report #{report_id} approved. Payment status set to UNPAID.")
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
    except Exception as e:
        print("[DEBUG][DECLINE][ERROR]", e)
        raise

    messages.success(request, f"Report #{report_id} declined. Payment status set to DECLINED.")
    return redirect("lupon_mem:report_review", report_id=report_id)



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
            "page_title": "Confirm & Open Case",
            "user_role": user_role,
            "initial_case_name": initial_case_name,
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
    except DatabaseError as e:
        messages.error(request, f"Failed to create case: {e}")
        return redirect("lupon_mem:report_confirm", report_id=report_id)
    except Exception:
        messages.error(request, "Unexpected error while creating case.")
        return redirect("lupon_mem:report_confirm", report_id=report_id)

    messages.success(request, f"Case #{case_id} created.")
    return redirect("lupon_mem:case_detail", case_id=case_id)



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

        # defaults for read-only selects (we still need IDs to POST, so we'll render hidden inputs)
        ct_id, ct_name = (complaint_titles[0][0], complaint_titles[0][1]) if complaint_titles else (None, "")
        cn_id, cn_name = (case_natures[0][0], case_natures[0][1]) if case_natures else (None, "")

        # settlement defaults to PENDING
        st_id, st_name = (None, "")
        for sid, sname in settlements:
            if str(sname).upper() == "PENDING":
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

            # lists kept only for safety; UI won’t expose them for editing
            "complaint_titles": complaint_titles,
            "case_natures": case_natures,
            "settlement_statuses": settlements,

            # payment UI
            "payment_statuses": payment_statuses,
            "default_or": _make_default_or(report_id),
            "default_amount": "150.00",
        }
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
        # when NOT recording payment, ensure we don’t pass stray values
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
        "FOR CASE FILING",
        "Report converted to case",
    ]
    print("[DEBUG][PAY-OPEN][POST] SQL → confirm_report_and_open_case(...) args:", args)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT confirm_report_and_open_case(
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s
            )""",
            args,
        )
        case_id = cur.fetchone()[0]

    messages.success(request, f"Case #{case_id} created.")
    return redirect("lupon_mem:case_detail", case_id=case_id)

