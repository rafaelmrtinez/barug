# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime

from lupon_mem.services.forms.kp8 import KP8Handler  # reuse its normalization
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler

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


# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}


# -----------------------------
# helper: slice fields by code
# -----------------------------
def _slice_until_code(fields_with_values: List[tuple], stop_code: str) -> List[tuple]:
    """
    Keep items up to and including the first one whose field_code == stop_code.
    Each item = (kff_id, field_id, label, type_name, is_required, value, field_code)
    """
    stop = (stop_code or "").strip().lower()
    if not stop:
        return fields_with_values
    out: List[tuple] = []
    for item in fields_with_values:
        out.append(item)
        code = (item[6] or "").strip().lower()
        if code == stop:
            break
    return out


def _get_person_mobile_number(person_id: int) -> str | None:
    """
    Returns a raw contact number (best effort) for a person.
    send_sms() will normalize it to 63XXXXXXXXXX.
    """
    try:
        with connection.cursor() as cur:
            # Try common columns on person
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='person'
                  AND column_name IN (
                    'mobile_number','mobile','phone','contact_no',
                    'contact','cellphone','cell_no','cellphone_no'
                  )
            """)
            cols = [r[0] for r in cur.fetchall()]

            if cols:
                selects = " , ".join([f"NULLIF({c},'') AS {c}" for c in cols])
                cur.execute(f"SELECT {selects} FROM person WHERE person_id=%s", [person_id])
                row = cur.fetchone()
                if row:
                    for val in row:
                        if isinstance(val, str) and val.strip():
                            return val.strip()

            # Optional: separate contact table (ignore if missing)
            try:
                cur.execute("""
                    SELECT NULLIF(c.contact_value,'')
                    FROM person_contact c
                    WHERE c.person_id=%s
                      AND LOWER(c.contact_type) IN ('mobile','phone','cell','cellphone')
                    ORDER BY c.person_contact_id DESC
                    LIMIT 1
                """, [person_id])
                r2 = cur.fetchone()
                if r2 and r2[0]:
                    return r2[0].strip()
            except Exception:
                pass
    except Exception:
        return None
    return None

    
# --- list cases (with safe search) ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_list(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()

    with connection.cursor() as cur:
        base_sql = """
            SELECT
                bc.blotter_case_id,                     -- 0
                bc.blotter_case_num,                    -- 1
                bc.blotter_case_name,                   -- 2
                to_char(bc.date_filed,'Mon DD, YYYY') AS date_filed_fmt,  -- 3
                COALESCE(ct.complaint_title_name,'—') AS complaint_title, -- 4
                COALESCE(cn.case_name,'—') AS case_nature                -- 5
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
        """
        order_limit = " ORDER BY bc.blotter_case_id DESC LIMIT 200"

        if q:
            cur.execute(
                base_sql
                + """
                WHERE
                    bc.blotter_case_num ILIKE CONCAT('%', %s, '%')
                 OR bc.blotter_case_name ILIKE CONCAT('%', %s, '%')
                 OR bc.incident_desc ILIKE CONCAT('%', %s, '%')
                """
                + order_limit,
                [q, q, q],
            )
        else:
            cur.execute(base_sql + order_limit)

        rows = cur.fetchall()

    return render(request, "lupon_mem/case_list.html", {"rows": rows, "q": q})


# --- case detail ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              bc.blotter_case_id,                                  -- 0
              bc.blotter_case_num,                                 -- 1
              bc.blotter_case_name,                                -- 2
              to_char(bc.date_filed,'Mon DD, YYYY') AS date_filed, -- 3
              bc.incident_desc,                                    -- 4
              COALESCE(ct.complaint_title_name,'—') AS type_name,  -- 5
              COALESCE(cn.case_name,'—') AS nature_name,           -- 6
              ss.settlement_status_name,                           -- 7  NEW
              bc.settlement_status_id                              -- 8  NEW
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn ON cn.case_nature_id   = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id=%s
            """,
            [case_id],
        )
        case = cur.fetchone()

        cur.execute(
            """
            SELECT
              s.submission_id, kf.form_code, kf.form_name, s.status,
              CASE WHEN s.submitted_at IS NULL THEN '—'
                   ELSE to_char(s.submitted_at,'Mon DD, YYYY HH12:MI AM')
              END AS submitted_fmt
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id=%s
            ORDER BY (s.submitted_at IS NULL), s.submitted_at DESC, s.submission_id DESC
            """,
            [case_id],
        )
        forms = cur.fetchall()

        # settlement choices for modal
        cur.execute("SELECT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_choices = [r[0] for r in cur.fetchall()]

    return render(
        request,
        "lupon_mem/case_detail.html",
        {
            "case": case,
            "forms": forms,
            "case_id": case_id,
            "settlement_choices": settlement_choices,  # NEW
        },
    )


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


# --- choose form (DB-backed; cached) ---
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
    return render(request, "lupon_mem/add_form_choose.html",
                  {"case_id": case_id, "forms": forms})


# --- split builder (left fields, right preview) ---
@session_login_required
@role_required(*LUPON_ROLES)
def form_builder(request, case_id: int, form_id: int = None, submission_id: int = None):
    """
    Split builder UI (left fields, right preview)

    Key behaviors:
      • Purpose/For = "<complaint_title> - <case_nature>".
      • Complaint Details ← incident_desc.
      • Address resolution (human-readable) from report if needed.
      • Date-derived fields from Date Filed (fallback: incident_date, then today).
      • Punong Barangay from role 'BARANGAY CAPTAIN' (fallback 'Lourdes Ramirez').
      • Mirrors: Complainant(s) – Alternate, Year Received – Alternate.
      • KP-9 page-2 split via first 'served_to'.
      • Default KP-7 view shows until 'solutions_seeked' (overridable with ?show_until=...).
      • NEW (KP-9): curr_date/curr_month/curr_year = TODAY; brgy_capt mirrors PB; respondent_names_* mirror respondents.
      • NEW (KP-9 Minimal): show only summons date & time with clearer labels.
    """


    with connection.cursor() as cur:
        # Header
        if submission_id:
            cur.execute(
                """
                SELECT s.submission_id, s.form_id, kf.form_code, kf.form_name
                  FROM blotter_kp_submission s
                  JOIN kp_form kf ON kf.form_id = s.form_id
                 WHERE s.submission_id=%s
                """,
                [submission_id],
            )
        else:
            cur.execute(
                "SELECT kf.form_id, kf.form_code, kf.form_name FROM kp_form kf WHERE kf.form_id=%s",
                [form_id],
            )
        hdr = cur.fetchone()
        if not hdr:
            return HttpResponseBadRequest("Form not found.")
        fid = hdr[1] if submission_id else hdr[0]
        form_code = hdr[2] if submission_id else hdr[1]
        form_name = hdr[3] if submission_id else hdr[2]

        # Fields
        cur.execute(
            """
            SELECT
                kff.kp_form_field_id,
                f.field_id,
                COALESCE(kff.label_override, f.base_label) AS label,
                t.field_type_name,
                kff.is_required,
                f.field_code
            FROM kp_form_field kff
            JOIN kp_field f      ON f.field_id = kff.field_id
            JOIN kp_field_type t ON t.field_type_id = f.field_type_id
            WHERE kff.form_id=%s
            ORDER BY kff.sort_order, kff.kp_form_field_id
            """,
            [fid],
        )
        fields = cur.fetchall()

        # Saved answers
        answers: Dict[str, Any] = {}
        if submission_id:
            cur.execute(
                "SELECT a.field_id, a.value_json FROM blotter_kp_answer a WHERE a.submission_id=%s",
                [submission_id],
            )
            for f_id, val in cur.fetchall():
                answers[str(f_id)] = val

        # Case + report link
        cur.execute(
            """
            SELECT
                bc.blotter_case_num,
                bc.incident_desc,
                bc.incident_date,
                bc.incident_time,
                bc.incident_location,
                bc.date_filed,
                ct.complaint_title_name,
                cn.case_name,
                bc.blotter_report_id
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
            """,
            [case_id],
        )
        row = cur.fetchone()
        (
            case_num, incident_desc, incident_date, incident_time,
            incident_loc_raw, date_filed,
            complaint_title_name, case_nature_name, blotter_report_id
        ) = row if row else (None,)*9

        # Resolve address (via blotter_report->addresss) if needed
        incident_addr_text = None
        if not incident_loc_raw and blotter_report_id:
            cur.execute(
                "SELECT incident_address_id FROM blotter_report WHERE blotter_report_id=%s",
                [blotter_report_id],
            )
            r = cur.fetchone()
            incident_address_id = r[0] if r else None
            if incident_address_id:
                cur.execute(
                    """
                    SELECT trim(
                             concat_ws(', ',
                               NULLIF(ps.purok_sitio_name,''),
                               NULLIF(a.street,''),
                               CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN 'Brgy. '||a.barangay ELSE NULL END,
                               NULLIF(a.city,'')
                             )
                           ) AS full_addr
                      FROM addresss a
                      LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                     WHERE a.address_id = %s
                    """,
                    [incident_address_id],
                )
                ar = cur.fetchone()
                incident_addr_text = (ar and ar[0]) or None

        incident_loc = (incident_loc_raw or incident_addr_text or "") or None

        # Parties
        cur.execute(
            """
            SELECT p.first_name, p.last_name
              FROM complainant_case cc
              JOIN person p ON p.person_id = cc.person_id
             WHERE cc.blotter_case_id=%s
             ORDER BY p.last_name, p.first_name
            """,
            [case_id],
        )
        cmps = ["%s %s" % (fn or "", ln or "") for fn, ln in cur.fetchall()]

        cur.execute(
            """
            SELECT p.first_name, p.last_name
              FROM respondent_case rc
              JOIN person p ON p.person_id = rc.person_id
             WHERE rc.blotter_case_id=%s
             ORDER BY p.last_name, p.first_name
            """,
            [case_id],
        )
        resps = ["%s %s" % (fn or "", ln or "") for fn, ln in cur.fetchall()]

        # Punong Barangay
        cur.execute(
            """
            SELECT trim(
                     coalesce(p.first_name,'') || ' ' ||
                     coalesce(p.middle_name,'') || ' ' ||
                     coalesce(p.last_name,'')  || ' ' ||
                     coalesce(p.suffix,'')
                   ) AS name
              FROM staff s
              JOIN person p ON p.person_id = s.person_id
              JOIN rolee  r ON r.role_id   = s.role_id
             WHERE r.role_name = 'BARANGAY CAPTAIN'
             ORDER BY s.staff_id DESC
             LIMIT 1
            """
        )
        row_pb = cur.fetchone()
        punong_barangay = (row_pb[0].strip() if row_pb and row_pb[0] else "") or "Lourdes Ramirez"

        # Helpers
        def _iso_date(d):
            try:
                return d.isoformat()
            except Exception:
                return None

        def _hm(t):
            try:
                return t.strftime("%H:%M")
            except Exception:
                return None

        def _fmt_purpose(ct_name: Optional[str], cn_name: Optional[str]) -> str:
            a = (ct_name or "").strip(); b = (cn_name or "").strip()
            return f"{a} - {b}" if a and b else (a or b or "")

        # Date sources
        from datetime import date as _date_cls, datetime as _dt_cls
        src_date = date_filed or incident_date or _date_cls.today()  # used for KP-7 etc.
        try:
            if isinstance(src_date, str):
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        src_date = _dt_cls.strptime(src_date, fmt).date()
                        break
                    except Exception:
                        pass
            if not hasattr(src_date, "year"):
                src_date = _date_cls.today()
        except Exception:
            src_date = _date_cls.today()

        date_created_iso = _iso_date(src_date) or _date_cls.today().isoformat()
        month_created    = src_date.strftime("%B")
        year_received    = str(src_date.year)
        month_received   = month_created

        # --- TODAY (KP-9 "current" stamps) ---
        today = _date_cls.today()
        curr_date_iso = today.isoformat()
        curr_month    = today.strftime("%B")
        curr_year     = str(today.year)

        parties_complainant = ", ".join([x.strip() for x in cmps if x.strip()])
        parties_respondent  = ", ".join([x.strip() for x in resps if x.strip()])
        first_respondent    = (resps[0].strip() if resps else "")
        for_value           = _fmt_purpose(complaint_title_name, case_nature_name)

        # Label-based prefill
        prefill_by_label: Dict[str, Any] = {
            "complainant(s)": parties_complainant,
            "complainants": parties_complainant,
            "respondent(s)": parties_respondent,
            "respondents": parties_respondent,

            # alternates (hyphen/en dash)
            "complainant(s) - alternate": parties_complainant,
            "complainants - alternate": parties_complainant,
            "complainant(s) – alternate": parties_complainant,
            "complainants – alternate": parties_complainant,

            # case no
            "barangay case no.": (case_num or ""),
            "brgy case number": (case_num or ""),
            "brgy case no.": (case_num or ""),
            "case number": (case_num or ""),
            "case no.": (case_num or ""),

            # purpose
            "for": for_value,
            "purpose": for_value,

            # incident/meta + complaint
            "complaint details": (incident_desc or ""),
            "complaint": (incident_desc or ""),
            "incident description": (incident_desc or ""),
            "incident date": _iso_date(incident_date) or "",
            "incident time": _hm(incident_time) or "",
            "incident location": (incident_loc or ""),

            # derived dates (from src_date)
            "date created": date_created_iso,
            "month created": month_created,
            "year received": year_received,
            "month received": month_received,

            # alt label for Year Received
            "year received - alternate": year_received,
            "year received – alternate": year_received,

            # captain (label-side)
            "punong barangay": punong_barangay,
            "barangay captain": punong_barangay,
            "chairman": punong_barangay,
            "brgy capt": punong_barangay,

            # KP-9 "current" stamps via label variants (just in case)
            "current date": curr_date_iso,
            "current month": curr_month,
            "current year": curr_year,

            # generic
            "date signed": date_created_iso,
            "recipient": first_respondent,
        }

        # Code-based prefill
        prefill_by_code: Dict[str, Any] = {
            # Universals
            "complainants": parties_complainant,
            "respondents": parties_respondent,
            "brgy_case_number": (case_num or ""),
            "brgy_case_num": (case_num or ""),
            "case_num": (case_num or ""),

            "purpose": for_value,

            "complaint_details": (incident_desc or ""),
            "incident_date": _iso_date(incident_date) or "",
            "incident_time": _hm(incident_time) or "",
            "incident_location": (incident_loc or ""),

            "date_created": date_created_iso,
            "month_created": month_created,
            "year_received": year_received,
            "month_received": month_received,

            # mirrors by code
            "complainants_2": parties_complainant,
            "year_received_2": year_received,

            "punong_barangay": punong_barangay,
            "date_signed": date_created_iso,

            # KP-9 specifics
            "recipient": first_respondent,
            "respondent_names_one": parties_respondent,
            "respondent_names_two": parties_respondent,
            "respondent_names_three": parties_respondent,

            # NEW: KP-9 "current" fields (explicitly TODAY, not src_date)
            "curr_date":  curr_date_iso,
            "curr_month": curr_month,
            "curr_year":  curr_year,

            # NEW: KP-9 brgy captain code mirrors PB
            "brgy_capt": punong_barangay,

            # ---------- KP-12: Notice of Hearing (Conciliation) ----------
            # parties (note: PDF uses 'repondents_one' typo)
            "complainants_one": parties_complainant,
            "repondents_one":   parties_respondent,     # keep typo to match PDF field_code if ever used as code
            "complainants_two": parties_complainant,
            "respondents_two":  parties_respondent,

            # created stamps from src_date
            "time_created": _hm(incident_time) or None,

            # TODAY stamps (current_*)
            "current_date":  curr_date_iso,
            "current_month": curr_month,
            "current_year":  curr_year,

            # notified stamps default to TODAY
            "notified_date":  curr_date_iso,
            "notified_month": curr_month,
            "notified_year":  curr_year,

            # captain field name used by KP-12
            "brgy_captain": punong_barangay,
        }

    # choose value: saved answer > label prefill > code prefill > ""
    def _ans_or_prefill(field_id, label, code):
        v = answers.get(str(field_id))
        if v not in (None, "", "null"):
            return v
        key = (label or "").strip().lower()
        if key in prefill_by_label:
            return prefill_by_label[key]
        ckey = (code or "").strip().lower()
        return prefill_by_code.get(ckey, "")

    # final list
    fields_with_values = [
        (
            kff_id, field_id, label, type_name, is_required,
            _ans_or_prefill(field_id, label, field_code),
            field_code,
        )
        for (kff_id, field_id, label, type_name, is_required, field_code) in fields
    ]

    # KP-9 page 2 split (for full mode)
    page2_index = None
    for idx, (_kff, _fid, _lbl, _typ, _req, _val, code) in enumerate(fields_with_values, start=1):
        if (code or "").strip().lower() == "served_to":
            page2_index = idx
            break

    # NEW: show only until a specific field_code (default for KP-7)
    stop_code = request.GET.get("show_until")
    if not stop_code and str(fid) == "7":
        stop_code = "solutions_seeked"
    if stop_code:
        fields_with_values = _slice_until_code(fields_with_values, stop_code)

    # -----------------------------
    # NEW: KP-9 Minimal UI
    # -----------------------------
    # UI-only flags: hide specific fields in the template (we pass all fields here)
    kp9_ui_minimal  = (str(form_code).strip().upper() == "KP-9")
    kp8_ui_minimal  = (str(form_code).strip().upper() == "KP-8")
    kp10_ui_minimal = (str(form_code).strip().upper() == "KP-10")
    kp11_ui_minimal = (str(form_code).strip().upper() == "KP-11")
    kp12_ui_minimal = (str(form_code).strip().upper() == "KP-12")  # optional flag (banner/hide if template supports it)
    kp13_ui_minimal = (str(form_code).strip().upper() == "KP-13")  # optional flag (banner/hide if template supports it)
    kp14_ui_minimal = (str(form_code).strip().upper() == "KP-14")  # optional flag (banner/hide if template supports it)
    kp15_ui_minimal = (str(form_code).strip().upper() == "KP-15")
    kp16_ui_minimal = (str(form_code).strip().upper() == "KP-16")
    kp17_ui_minimal = (str(form_code).strip().upper() == "KP-17")  # optional flag (banner/hide if template supports it)
    kp18_ui_minimal = (str(form_code).strip().upper() == "KP-18")  # optional flag (banner/hide if template supports it)
    kp19_ui_minimal = (str(form_code).strip().upper() == "KP-19")  # optional flag (banner/hide if template supports it)
    kp20_ui_minimal = (str(form_code).strip().upper() == "KP-20")
    kp21_ui_minimal = (str(form_code).strip().upper() == "KP-21")
    kp22_ui_minimal = (str(form_code).strip().upper() == "KP-22")  # optional flag (banner/hide if template supports it)
    kp23_ui_minimal = (str(form_code).strip().upper() == "KP-23")  # optional flag (banner/hide if template supports it)
    kp24_ui_minimal = (str(form_code).strip().upper() == "KP-24")  # optional flag (banner/hide if template supports it)
    kp25_ui_minimal = (str(form_code).strip().upper() == "KP-25")
    kp26_ui_minimal = (str(form_code).strip().upper() == "KP-26")

    return render(
        request,
        "lupon_mem/form_builder.html",
        {
            "case_id": case_id,
            "submission_id": submission_id,
            "form_id": fid,
            "header": hdr,
            "fields": fields_with_values,
            "answers": answers,
            "page2_index": page2_index,
            "stop_code": stop_code,          # pass to template for hint
            "kp9_ui_minimal": kp9_ui_minimal,   # UI-only flag; no field pruning
            "kp8_ui_minimal": kp8_ui_minimal,
            "kp10_ui_minimal": kp10_ui_minimal,
            "kp11_ui_minimal": kp11_ui_minimal,
            "kp12_ui_minimal": kp12_ui_minimal,  # new (template may ignore if not used)
            "kp13_ui_minimal": kp13_ui_minimal,  # new (template may ignore if not used)
            "kp14_ui_minimal": kp14_ui_minimal,
            "kp15_ui_minimal": kp15_ui_minimal,
            "kp16_ui_minimal": kp16_ui_minimal,  # new (template may ignore if not used)
            "kp17_ui_minimal": kp17_ui_minimal,  # new (template may ignore if not used)
            "kp18_ui_minimal": kp18_ui_minimal,  # new (template may ignore if not used)
            "kp19_ui_minimal": kp19_ui_minimal,
            "kp20_ui_minimal": kp20_ui_minimal,
            "kp21_ui_minimal": kp21_ui_minimal,  # new (template may ignore if not used)
            "kp22_ui_minimal": kp22_ui_minimal,  # new (template may ignore if not used).
            "kp23_ui_minimal": kp23_ui_minimal,  # new (template may ignore if not used)
            "kp24_ui_minimal": kp24_ui_minimal,
            "kp25_ui_minimal": kp25_ui_minimal,
            "kp26_ui_minimal": kp26_ui_minimal,  # new (template may ignore if not used)
        },
    )

# --- AJAX: save answers ---
@role_required(*LUPON_ROLES)
@session_login_required
def save_answers(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    data = request.POST
    case_id = int(data["case_id"])
    form_id = int(data["form_id"])
    submission_id = data.get("submission_id")

    import json as _json
    payload = _json.loads(data["answers"])  # {field_id: value}

    with transaction.atomic():
        with connection.cursor() as cur:
            if submission_id:
                sid = int(submission_id)
            else:
                cur.execute(
                    """
                  INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
                  VALUES (%s,%s,'DRAFT') RETURNING submission_id
                """,
                    [case_id, form_id],
                )
                sid = cur.fetchone()[0]

            for field_id, value in payload.items():
                cur.execute(
                    """
                  INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                  VALUES (%s,%s,%s)
                  ON CONFLICT (submission_id, field_id)
                  DO UPDATE SET value_json=EXCLUDED.value_json
                """,
                    [sid, int(field_id), _json.dumps(value)],
                )

    return JsonResponse({"ok": True, "submission_id": sid})


# --- AJAX: submit & generate PDF ---
# --- AJAX: submit & generate PDF ---
# --- AJAX: submit & generate PDF ---
@role_required(*LUPON_ROLES)
@session_login_required
def submit_form(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    import json as _json
    import logging
    from datetime import datetime as _dt
    log = logging.getLogger(__name__)

    data = _json.loads(request.body.decode())
    submission_id = int(data["submission_id"])
    case_id = int(data["case_id"])

    # --- Helper: best-effort pull of a person's mobile number (raw; send_sms would normalize)
    def _get_person_mobile_number(person_id: int) -> str | None:
        try:
            with connection.cursor() as cur:
                # Try common columns on person (trimmed to what's in your DB)
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='person'
                      AND column_name IN ('mobile_num')
                """)
                cols = [r[0] for r in cur.fetchall()]
                if cols:
                    selects = " , ".join([f"NULLIF({c},'') AS {c}" for c in cols])
                    cur.execute(f"SELECT {selects} FROM person WHERE person_id=%s", [person_id])
                    row = cur.fetchone()
                    if row:
                        for val in row:
                            if isinstance(val, str) and val.strip():
                                return val.strip()

                # Optional: separate contact table (ignore if missing)
                try:
                    cur.execute("""
                        SELECT NULLIF(c.contact_value,'')
                        FROM person_contact c
                        WHERE c.person_id=%s
                          AND LOWER(c.contact_type) IN ('mobile','phone','cell','cellphone')
                        ORDER BY c.person_contact_id DESC
                        LIMIT 1
                    """, [person_id])
                    r2 = cur.fetchone()
                    if r2 and r2[0]:
                        return r2[0].strip()
                except Exception:
                    pass
        except Exception:
            return None
        return None

    # --- Render the final PDF bytes & filename
    try:
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        # Validation errors should surface to the UI
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception:
        log.exception("submit_form render_final_pdf failed")
        return JsonResponse({"ok": False, "error": "Failed to generate PDF."}, status=500)

    # --- Upload to Supabase (best-effort; we still return the local download link)
    bucket = getattr(settings, "SUPABASE_BUCKET", "documents")
    path = f"blotter/{case_id}/{filename}"
    storage_url = None
    try:
        supabase.storage.from_(bucket).upload(
            path,
            pdf_bytes,
            {
                "contentType": "application/pdf",
                "upsert": "true",
            },
        )
        try:
            pub = supabase.storage.from_(bucket).get_public_url(path)
            if isinstance(pub, dict):
                storage_url = pub.get("publicUrl") or pub.get("public_url")
            elif isinstance(pub, str):
                storage_url = pub
        except Exception:
            storage_url = None

        if not storage_url:
            try:
                signed = supabase.storage.from_(bucket).create_signed_url(path, 60 * 60 * 24 * 7)
                if isinstance(signed, dict):
                    storage_url = (
                        signed.get("signedURL")
                        or signed.get("signedUrl")
                        or signed.get("signed_url")
                    )
            except Exception:
                storage_url = None
    except Exception:
        storage_url = None

    # --- Mark submission as submitted
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s",
            [submission_id],
        )

    # --- Build local download URL (always available)
    local_download = request.build_absolute_uri(
        reverse("lupon_mem:submission_pdf", args=[submission_id])
    )

    # --- KP-8 / KP-10 / KP-11 notifications (in-app only; SMS is disabled below)
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT s.form_id, kf.form_code
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.submission_id=%s
            """, [submission_id])
            row = cur.fetchone()
        form_id, form_code = (int(row[0]), str(row[1]).upper()) if row else (None, "")

        # ------------------ KP-8: Notice of Hearing ------------------
        if form_code == "KP-8":
            # Build name→value map via the handler (mirrors what the PDF used)
            nv = KP8Handler().build_name_value_map(form_id=form_id, submission_id=submission_id)

            # Case number for context
            with connection.cursor() as cur:
                cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                r_case = cur.fetchone()
            case_no = r_case[0] if r_case else None

            # Extract schedule pieces exactly as placed on PDF
            day   = (nv.get("appearance_date")  or "").strip()
            month = (nv.get("appearance_month") or "").strip()
            year  = (nv.get("appearance_year")  or "").strip()
            time_ = (nv.get("appearance_time")  or "").strip()
            venue = (nv.get("appear_to") or nv.get("venue") or "").strip()

            # Human-friendly string (e.g., "October 07, 2025 at 14:00")
            parts = []
            if month and day and year:
                try:
                    parts.append(f"{month} {int(day):02d}, {year}")
                except Exception:
                    parts.append(f"{month} {day}, {year}")
            elif month and day:
                parts.append(f"{month} {day}")
            elif month and year:
                parts.append(f"{month} {year}")
            elif year:
                parts.append(year)
            if time_:
                parts.append(f"at {time_}")
            if venue:
                parts.append(f"({venue})")
            when_text = " ".join(parts) if parts else "on the scheduled date"

            title = f"Notice of Hearing — Case {case_no}" if case_no else "Notice of Hearing"
            body_app = f"You are required to appear {when_text} for your mediation hearing."
            if case_no:
                body_app += f" (Case {case_no})"
            # body_sms = f"Barangay Notice: Hearing {when_text}. Please appear." + (f" Case {case_no}." if case_no else "")

            # -------- collect target person_ids --------
            person_ids: set[int] = set()

            # Respondents
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,''))
                    FROM respondent_case rc
                    JOIN person p ON p.person_id = rc.person_id
                    WHERE rc.blotter_case_id = %s
                """, [case_id])
                for pid, _nm in cur.fetchall():
                    if pid:
                        person_ids.add(int(pid))

            # Complainants
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,''))
                    FROM complainant_case cc
                    JOIN person p ON p.person_id = cc.person_id
                    WHERE cc.blotter_case_id = %s
                """, [case_id])
                for pid, _nm in cur.fetchall():
                    if pid:
                        person_ids.add(int(pid))

            # Names typed/prefilled on KP-8 → resolve to person_id (best-effort)
            name_blobs = [
                nv.get("recipient") or "",
                nv.get("recipient_2") or "",
                nv.get("respondents") or "",
                nv.get("complainants") or "",
                nv.get("complainants_2") or "",
            ]
            raw_names: list[str] = []
            for blob in name_blobs:
                for piece in (blob or "").replace(";", ",").split(","):
                    nm = piece.strip()
                    if nm:
                        raw_names.append(nm)

            def _find_person_id_by_name(name: str) -> Optional[int]:
                try:
                    parts = [p for p in name.split() if p]
                    with connection.cursor() as cur:
                        if len(parts) >= 2:
                            first, last = parts[0], parts[-1]
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name ILIKE %s AND last_name ILIKE %s)
                                   OR ( (first_name || ' ' || COALESCE(middle_name,'') || ' ' || last_name) ILIKE %s )
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [first, last, f"%{name}%"])
                        else:
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name || ' ' || last_name) ILIKE %s
                                   OR last_name ILIKE %s
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [f"%{name}%", f"%{name}%"])
                        r = cur.fetchone()
                        return int(r[0]) if r and r[0] else None
                except Exception:
                    return None

            for nm in raw_names:
                pid = _find_person_id_by_name(nm)
                if pid:
                    person_ids.add(pid)

            # In-app notifications only
            for pid in sorted(person_ids):
                try:
                    notify_user(
                        user_type_id=1,     # 1 = RESIDENT
                        person_id=pid,
                        staff_id=None,
                        title=title,
                        body=body_app,
                        deep_link=f"/resident/cases/{case_id}"
                    )
                except Exception:
                    log.exception("notify_user failed for person_id=%s case_id=%s", pid, case_id)

            # -------- SMS disabled ----------
            # numbers = [n for pid in sorted(person_ids) if (n := _get_person_mobile_number(pid))]
            # if numbers:
            #     try:
            #         res = send_sms(to=numbers, message=body_sms, fail_silently=True, dry_run=False)
            #         ok = getattr(res, "ok", False)
            #         detail = getattr(res, "detail", None)
            #         log.info("KP-8 SMS result ok=%s detail=%s", ok, detail)
            #     except Exception:
            #         log.exception("KP-8 SMS send raised unexpectedly")
            # else:
            #     log.info("KP-8: no mobile numbers found for any targets (case_id=%s)", case_id)

        # ------------------ KP-10: Notice for Constitution of Pangkat ------------------
        elif form_code == "KP-10":
            from lupon_mem.services.forms.kp10 import KP10Handler  # ensure available
            nv = KP10Handler().build_name_value_map(form_id=form_id, submission_id=submission_id)

            # Case number (optional context)
            with connection.cursor() as cur:
                cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                r_case = cur.fetchone()
            case_no = r_case[0] if r_case else None

            # Human-friendly schedule using KP-10 fields
            day_raw  = (nv.get("appearance_date") or "").strip()   # often ISO-like date
            year_raw = (nv.get("current_year") or "").strip()
            time_raw = (nv.get("appearance_time") or "").strip()
            venue    = (nv.get("appear_to") or "").strip()

            parts = []
            try:
                d = _dt.strptime(day_raw, "%Y-%m-%d").date()
                parts.append(d.strftime("%B %d, %Y"))
            except Exception:
                if day_raw and year_raw and year_raw not in day_raw:
                    parts.append(f"{day_raw}, {year_raw}")
                elif day_raw:
                    parts.append(day_raw)
                elif year_raw:
                    parts.append(year_raw)
            if time_raw:
                parts.append(f"at {time_raw}")
            if venue:
                parts.append(f"({venue})")
            when_text = " ".join(parts) if parts else "on the scheduled date"

            title = f"Notice for Constitution of Pangkat — Case {case_no}" if case_no else "Notice for Constitution of Pangkat"
            body_app = f"You are required to appear {when_text} for the constitution of the Pangkat."
            if case_no:
                body_app += f" (Case {case_no})"
            # body_sms = f"Barangay Notice: Pangkat constitution {when_text}. Please appear." + (f" Case {case_no}." if case_no else "")

            # Targets = respondents + complainants + any typed names in KP-10
            person_ids: set[int] = set()

            # Respondents
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id
                    FROM respondent_case rc
                    JOIN person p ON p.person_id = rc.person_id
                    WHERE rc.blotter_case_id = %s
                """, [case_id])
                person_ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

            # Complainants
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id
                    FROM complainant_case cc
                    JOIN person p ON p.person_id = cc.person_id
                    WHERE cc.blotter_case_id = %s
                """, [case_id])
                person_ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

            # Names typed on the form (best-effort match)
            name_blobs = [
                nv.get("addr_to") or "",
                nv.get("complainants") or "",
                nv.get("complainants_2") or "",
                nv.get("respondents") or "",
                nv.get("respondents_2") or "",
            ]
            raw_names: list[str] = []
            for blob in name_blobs:
                for piece in (blob or "").replace(";", ",").split(","):
                    nm = piece.strip()
                    if nm:
                        raw_names.append(nm)

            def _find_person_id_by_name(name: str) -> Optional[int]:
                try:
                    parts = [p for p in name.split() if p]
                    with connection.cursor() as cur:
                        if len(parts) >= 2:
                            first, last = parts[0], parts[-1]
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name ILIKE %s AND last_name ILIKE %s)
                                   OR ((first_name || ' ' || COALESCE(middle_name,'') || ' ' || last_name) ILIKE %s)
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [first, last, f"%{name}%"])
                        else:
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name || ' ' || last_name) ILIKE %s
                                   OR last_name ILIKE %s
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [f"%{name}%", f"%{name}%"])
                        r = cur.fetchone()
                        return int(r[0]) if r and r[0] else None
                except Exception:
                    return None

            for nm in raw_names:
                pid = _find_person_id_by_name(nm)
                if pid:
                    person_ids.add(pid)

            # In-app notifications only
            for pid in sorted(person_ids):
                try:
                    notify_user(
                        user_type_id=1,
                        person_id=pid,
                        staff_id=None,
                        title=title,
                        body=body_app,
                        deep_link=f"/resident/cases/{case_id}"
                    )
                except Exception:
                    log.exception("KP-10 notify_user failed for person_id=%s case_id=%s", pid, case_id)

            # -------- SMS disabled ----------
            # numbers = [n for pid in sorted(person_ids) if (n := _get_person_mobile_number(pid))]
            # if numbers:
            #     try:
            #         res = send_sms(to=numbers, message=body_sms, fail_silently=True, dry_run=False)
            #         ok = getattr(res, "ok", False)
            #         status = getattr(res, "status", None)
            #         detail = getattr(res, "detail", None)
            #         log.info("KP-10 SMS result ok=%s status=%s detail=%s", ok, status, detail)
            #     except Exception:
            #         log.exception("KP-10 SMS send raised unexpectedly")
            # else:
            #     log.info("KP-10: no mobile numbers found for any targets (case_id=%s)", case_id)

        # ------------------ KP-11: Notice to Chosen Pangkat Member ------------------
        elif form_code == "KP-11":
            nv = KP11Handler().build_name_value_map(form_id=form_id, submission_id=submission_id)

            # Case number (optional)
            with connection.cursor() as cur:
                cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                r_case = cur.fetchone()
            case_no = r_case[0] if r_case else None

            # Build human-friendly “when” text using KP-11 fields
            day_raw   = (nv.get("rcvd_date") or "").strip()         # e.g., "7"
            month_raw = (nv.get("rcvd_month") or "").strip()        # e.g., "October"
            # (date_today may be ISO; we don’t need it for the phrase)
            parts = []
            if month_raw and day_raw:
                try:
                    parts.append(f"{month_raw} {int(day_raw):02d}")
                except Exception:
                    parts.append(f"{month_raw} {day_raw}")
            elif month_raw:
                parts.append(month_raw)

            when_text = " ".join(parts) if parts else "on the indicated date"

            title = f"Notice to Chosen Pangkat Member — Case {case_no}" if case_no else \
                    "Notice to Chosen Pangkat Member"
            body_app = f"You have been chosen as Pangkat member; please take note of the notice {when_text}."
            if case_no:
                body_app += f" (Case {case_no})"

            # Collect targets: respondents + complainants + explicit recipient/pangkat member names
            person_ids: set[int] = set()

            # Respondents
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id
                    FROM respondent_case rc
                    JOIN person p ON p.person_id = rc.person_id
                    WHERE rc.blotter_case_id = %s
                """, [case_id])
                person_ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

            # Complainants
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT p.person_id
                    FROM complainant_case cc
                    JOIN person p ON p.person_id = cc.person_id
                    WHERE cc.blotter_case_id = %s
                """, [case_id])
                person_ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

            # Names typed on KP-11 (recipient and pangkat member)
            name_blobs = [
                nv.get("recepient") or "",              # PDF typo field
                nv.get("pangkat_member_name") or "",
            ]
            raw_names: list[str] = []
            for blob in name_blobs:
                for piece in (blob or "").replace(";", ",").split(","):
                    nm = piece.strip()
                    if nm:
                        raw_names.append(nm)

            def _find_person_id_by_name(name: str) -> Optional[int]:
                try:
                    parts = [p for p in name.split() if p]
                    with connection.cursor() as cur:
                        if len(parts) >= 2:
                            first, last = parts[0], parts[-1]
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name ILIKE %s AND last_name ILIKE %s)
                                   OR ((first_name || ' ' || COALESCE(middle_name,'') || ' ' || last_name) ILIKE %s)
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [first, last, f"%{name}%"])
                        else:
                            cur.execute("""
                                SELECT person_id
                                FROM person
                                WHERE (first_name || ' ' || last_name) ILIKE %s
                                   OR last_name ILIKE %s
                                ORDER BY person_id DESC
                                LIMIT 1
                            """, [f"%{name}%", f"%{name}%"])
                        r = cur.fetchone()
                        return int(r[0]) if r and r[0] else None
                except Exception:
                    return None

            for nm in raw_names:
                pid = _find_person_id_by_name(nm)
                if pid:
                    person_ids.add(pid)

            # In-app notifications only (SMS disabled, like KP-8/KP-10)
            for pid in sorted(person_ids):
                try:
                    notify_user(
                        user_type_id=1,  # RESIDENT
                        person_id=pid,
                        staff_id=None,
                        title=title,
                        body=body_app,
                        deep_link=f"/resident/cases/{case_id}"
                    )
                except Exception:
                    log.exception("KP-11 notify_user failed for person_id=%s case_id=%s", pid, case_id)

    except Exception:
        log.exception("KP-8/KP-10 notifications failed for submission %s", submission_id)

    # --- Done
    return JsonResponse(
        {
            "ok": True,
            "file": filename,
            "download_url": local_download,
            "storage_url": storage_url,
        }
    )


# --- preview image (PNG) ---
@session_login_required
@role_required(*LUPON_ROLES)
def preview_image(request: HttpRequest):
    form_id = int(request.GET["form_id"])
    submission_id = request.GET.get("submission_id")
    answers_json = request.GET.get("answers")
    img_bytes = render_preview_png(
        form_id=form_id, submission_id=submission_id, answers_json=answers_json
    )
    return HttpResponse(img_bytes, content_type="image/png")


# --- Dashboard ---
@session_login_required
@role_required(*LUPON_ROLES)
@nocache
def dashboard(request: HttpRequest):
    auth = request.session.get("auth")
    return render(
        request,
        "lupon_mem/dashboard.html",
        {
            "page_path": f"Barangay Lupon Member/Dashboard",
            "page_title": "Dashboard",
            "auth": auth,
        },
    )


# Helpers reused by case_new/report flows
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


def _toi(x):
    try:
        return int(x) if x not in (None, "", "0") else None
    except Exception:
        return None


# @session_login_required
# @role_required(*LUPON_ROLES, "barangay treasurer")
# def report_list(request: HttpRequest):
#     q_raw = (request.GET.get("q") or "").strip()

#     with connection.cursor() as cur:
#         base_sql = """
#             SELECT
#               br.blotter_report_id,                                       -- 0
#               br.incident_subject,                                        -- 1
#               to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at, -- 2

#               -- Latest payment status from blotter_report_payment (fallback to report column if you added it)
#               COALESCE(lat.pay_status, reps.pay_status, '—') AS pay_status -- 3
#             FROM blotter_report br

#             -- latest transaction status (by payment row)
#             LEFT JOIN LATERAL (
#               SELECT ps.payment_status_name AS pay_status
#                 FROM blotter_report_payment rp
#                 JOIN payment_status ps ON ps.payment_status_id = rp.payment_status_id
#                WHERE rp.blotter_report_id = br.blotter_report_id
#                ORDER BY rp.date_of_payment DESC, rp.blotter_report_payment_id DESC
#                LIMIT 1
#             ) AS lat ON TRUE

#             -- (optional) report-level status column if present in schema
#             LEFT JOIN LATERAL (
#               SELECT ps2.payment_status_name AS pay_status
#                 FROM payment_status ps2
#                WHERE ps2.payment_status_id = br.payment_status_id
#                LIMIT 1
#             ) AS reps ON TRUE
#         """

#         order_limit = " ORDER BY br.date_time_reported DESC LIMIT 200"

#         if q_raw:
#             cur.execute(
#                 base_sql
#                 + """
#                 WHERE br.incident_subject ILIKE CONCAT('%', %s, '%')
#                 """
#                 + order_limit,
#                 [q_raw],
#             )
#         else:
#             cur.execute(base_sql + order_limit)

#         rows = cur.fetchall()

#     return render(request, "lupon_mem/report_list.html", {"rows": rows, "q": q_raw})



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


from django.db import DatabaseError

def _toi(x):
    try:
        return int(x) if x not in (None, "", "0") else None
    except Exception:
        return None


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
@role_required(*LUPON_ROLES)
def submission_pdf(request: HttpRequest, submission_id: int):
    try:
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return HttpResponse(str(e), status=400)
    except Exception:
        return HttpResponse("Failed to generate PDF.", status=500)

    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# add near the top with your other imports
from lupon_mem.services.timeline import get_case_timeline

# --- Case timeline (read-only) ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_timeline(request: HttpRequest, case_id: int):
    data = get_case_timeline(case_id)
    if not data.get("header"):
        return HttpResponseBadRequest("Case not found.")
    return render(request, "lupon_mem/case_timeline.html", data)


# --- lightweight staff suggest for officer picker (KP-9 offcr_name) ---
@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'') || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id = s.role_id
            WHERE (r.role_name IN ('BARANGAY LUPON MEMBER','BARANGAY LUPON PRESIDENT'))
              AND (
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || p.last_name) ILIKE %s
              )
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like],
        )
        rows = cur.fetchall()

    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})


# --- zero-DB chooser using constants ---
@session_login_required
@role_required(*LUPON_ROLES)
def add_form_choose_static(request: HttpRequest, case_id: int):
    """
    Zero-DB chooser. Uses hard-coded KP_FORMS_CATALOG (code, name).
    """
    return render(
        request,
        "lupon_mem/add_form_choose_static.html",
        {"case_id": case_id, "forms": KP_FORMS_CATALOG},
    )


@session_login_required
@role_required(*LUPON_ROLES)
def form_builder_by_code(request: HttpRequest, case_id: int, form_code: str):
    """
    Resolve form_id by form_code (unique) then reuse existing form_builder.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT form_id
            FROM kp_form
            WHERE form_code = %s AND is_active IS TRUE
        """, [form_code])
        row = cur.fetchone()
    if not row:
        return HttpResponseNotFound(f"Form {form_code} not found or inactive.")
    form_id = int(row[0])
    return redirect("lupon_mem:form_builder", case_id=case_id, form_id=form_id)

# --- lightweight person suggest for subpoena_to / subpoena_witness (KP-13) ---
@session_login_required
@role_required(*LUPON_ROLES)
def person_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT p.person_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'')  || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM person p
            WHERE
                 p.first_name ILIKE %s
              OR p.last_name  ILIKE %s
              OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like],
        )
        rows = cur.fetchall()

    return JsonResponse({"results": [{"id": r[0], "name": (r[1] or "").strip()} for r in rows]})


# @session_login_required
# @role_required(*LUPON_ROLES)
# def report_approve(request, report_id: int):
#     """Lupon member approves a report -> sets payment UNPAID."""
#     if request.method != "POST":
#         return HttpResponseBadRequest("Method not allowed.")

#     staff_id = (request.session.get("auth") or {}).get("staff_id")
#     if not staff_id:
#         return HttpResponseBadRequest("No staff id in session.")

#     with connection.cursor() as cur:
#         cur.execute(
#             "SELECT approve_report_set_unpaid(%s,%s,%s)",
#             [report_id, staff_id, "Approved for case payment"]
#         )
#     messages.success(request, f"Report #{report_id} approved. Payment status set to UNPAID.")
#     return redirect("lupon_mem:report_list")


# @session_login_required
# @role_required("barangay treasurer")
# def report_pay_and_open_case(request, report_id: int):
#     """Treasurer records payment -> instantly creates blotter case."""
#     if request.method == "GET":
#         # show a very small form to collect amount/OR and show read-only context
#         with connection.cursor() as cur:
#             cur.execute("""
#                 SELECT br.blotter_report_id,
#                        COALESCE(br.incident_subject,'(no subject)'),
#                        to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI'),
#                        ps.payment_status_name
#                   FROM blotter_report br
#                   LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
#                  WHERE br.blotter_report_id=%s
#             """,[report_id])
#             rpt = cur.fetchone()
#         return render(request, "lupon_mem/report_pay.html", {"rpt": rpt})

#     # POST: take payment and open case
#     staff_id = (request.session.get("auth") or {}).get("staff_id")
#     if not staff_id:
#         return HttpResponseBadRequest("No staff id in session.")

#     def _toi(x):
#         try:
#             return int(x) if str(x).strip() else None
#         except Exception:
#             return None

#     case_name            = request.POST.get("case_name") or "People vs."
#     complaint_title_id   = _toi(request.POST.get("complaint_title_id"))
#     case_nature_id       = _toi(request.POST.get("case_nature_id"))
#     settlement_status_id = _toi(request.POST.get("settlement_status_id"))
#     or_number            = (request.POST.get("payment_receipt") or "").strip() or None
#     amount               = request.POST.get("payment_amount") or "0"
#     paid_by_person_id    = _toi(request.POST.get("paid_by_person_id"))

#     with connection.cursor() as cur:
#         cur.execute("""
#             SELECT treasurer_pay_and_open_case(
#               %s,%s,%s,%s,%s,%s,%s,%s
#             )
#         """, [
#             report_id,
#             case_name,
#             complaint_title_id,
#             case_nature_id,
#             settlement_status_id,
#             or_number,
#             amount,
#             paid_by_person_id,
#             staff_id
#         ])
#         case_id = cur.fetchone()[0]

#     messages.success(request, f"Payment recorded. Case #{case_id} created.")
#     return redirect("lupon_mem:case_detail", case_id=case_id)



# ---------- CHANGED: report_list shows payment_status ----------
# helper to read role
def _user_role(request: HttpRequest) -> str:
    auth = request.session.get("auth") or {}
    return (auth.get("role_name") or auth.get("role") or "").strip()

# # 1) LIST: include user_role in context
# @session_login_required
# @role_required(*LUPON_ROLES, "barangay treasurer")
# def report_list(request: HttpRequest):
#     q_raw = (request.GET.get("q") or "").strip()
#     with connection.cursor() as cur:
#         cur.execute("""
#             SELECT
#               br.blotter_report_id,
#               COALESCE(br.incident_subject,'(no subject)'),
#               to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
#               ps.payment_status_name
#             FROM blotter_report br
#             LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
#             {}
#         """.format(
#             "WHERE br.incident_subject ILIKE CONCAT('%', %s, '%') ORDER BY br.date_time_reported DESC LIMIT 200"
#             if q_raw else "ORDER BY br.date_time_reported DESC LIMIT 200"
#         ), ([q_raw] if q_raw else [])
#         )
#         rows = cur.fetchall()
#     return render(
#         request,
#         "lupon_mem/report_list.html",
#         {"rows": rows, "q": q_raw, "user_role": _user_role(request)}
#     )

# # 2) REVIEW: bfoth roles can view; Lupon can approve/decline here
# @session_login_required
# @role_required(*LUPON_ROLES, "barangay treasurer")
# def report_review(request: HttpRequest, report_id: int):
#     role = _user_role(request)

#     # load report header, parties, payment status
#     with connection.cursor() as cur:
#         cur.execute("""
#             SELECT br.blotter_report_id,
#                    COALESCE(br.incident_subject,'(no subject)') AS subj,
#                    COALESCE(br.incident_desc,'') AS desc,
#                    to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
#                    ps.payment_status_name
#             FROM blotter_report br
#             LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
#             WHERE br.blotter_report_id=%s
#         """, [report_id])
#         rpt = cur.fetchone()
#         if not rpt:
#             return HttpResponseBadRequest("Report not found.")

#         cur.execute("""
#             SELECT p.person_id, trim(p.first_name||' '||p.last_name) AS name, 'COMPLAINANT' AS role
#               FROM complainant_report cr JOIN person p ON p.person_id=cr.person_id
#              WHERE cr.blotter_report_id=%s
#             UNION ALL
#             SELECT p.person_id, trim(p.first_name||' '||p.last_name), 'RESPONDENT'
#               FROM respondent_report rr JOIN person p ON p.person_id=rr.person_id
#              WHERE rr.blotter_report_id=%s
#              ORDER BY role, name
#         """, [report_id, report_id])
#         parties = cur.fetchall()

#     # If POST from the Approve button (Lupon)
#     if request.method == "POST" and role.upper() in LUPON_ROLES:
#         action = (request.POST.get("action") or "").lower()
#         note = (request.POST.get("note") or "").strip() or None
#         staff_id = (request.session.get("auth") or {}).get("staff_id")

#         if action == "approve":
#             with connection.cursor() as cur:
#                 cur.execute("SELECT approve_report_set_unpaid(%s,%s,%s)",
#                             [report_id, staff_id, "Approved for case payment"])
#             messages.success(request, f"Report #{report_id} approved (set to UNPAID).")
#             return redirect("lupon_mem:report_review", report_id=report_id)

#         if action == "decline":
#             # if you have a DB function; otherwise soft fallback shown below
#             try:
#                 with connection.cursor() as cur:
#                     cur.execute("SELECT decline_report(%s,%s,%s)", [report_id, staff_id, note])
#             except Exception:
#                 # Fallback: mark a simple status/flag if your schema has columns
#                 with connection.cursor() as cur:
#                     # Adjust these columns to your schema if different
#                     cur.execute("""
#                         UPDATE blotter_report SET payment_status_id = NULL, remarks = COALESCE(remarks,'') || %s
#                         WHERE blotter_report_id=%s
#                     """, [f"\nDeclined by staff {staff_id}: {note or '(no reason)'}", report_id])
#             messages.info(request, f"Report #{report_id} declined.")
#             return redirect("lupon_mem:report_review", report_id=report_id)

#     ctx = {
#         "page_title": "Review Report",
#         "report": rpt,        # (id, subject, desc, reported_at, pay_status)
#         "parties": parties,
#         "user_role": role,
#     }
#     return render(request, "lupon_mem/report_review.html", ctx)


# # ---------- NEW: LUPON approves → set UNPAID ----------
# @session_login_required
# @role_required(*LUPON_ROLES)
# def report_approve(request: HttpRequest, report_id: int):
#     if request.method != "POST":
#         return HttpResponseBadRequest("Method not allowed.")

#     staff_id = (request.session.get("auth") or {}).get("staff_id")
#     if not staff_id:
#         return HttpResponseBadRequest("Missing staff id.")

#     with connection.cursor() as cur:
#         # SQL function you created earlier
#         cur.execute("SELECT approve_report_set_unpaid(%s,%s,%s)", [report_id, staff_id, "Approved for case payment"])
#     messages.success(request, f"Report #{report_id} approved. Payment status set to UNPAID.")
#     return redirect("lupon_mem:report_list")


# # ---------- NEW: Treasurer pays & opens case ----------
# # --- Treasurer: Pay & Open Case ---
# # ---------- NEW: Treasurer pays & opens case ----------
# # --- Treasurer: Pay & Open Case ---
# @session_login_required
# @role_required(*LUPON_ROLES, "barangay treasurer")
# def report_pay_and_open_case(request: HttpRequest, report_id: int):
#     """
#     For the BARANGAY TREASURER only.
#     Mirrors the report_confirm UI but:
#       • Always shows payment controls (toggle-able)
#       • On submit, calls confirm_report_and_open_case(...) with with_payment flag
#       • If with_payment is ON and OR is blank, we auto-generate an OR and keep status PAID
#     """
#     from datetime import datetime
#     from decimal import Decimal

#     def _toi(x):
#         try:
#             return int(x) if (x is not None and str(x).strip() and str(x).strip() != "0") else None
#         except Exception:
#             return None

#     def _to_decimal(x, default="0"):
#         try:
#             return Decimal(str(x)) if (x is not None and str(x).strip()) else Decimal(default)
#         except Exception:
#             return Decimal(default)

#     def _make_default_or(rpt_id: int) -> str:
#         # OR-YYYYMMDD-HHMMSS-<report_id 5d>
#         return f"OR-{datetime.now():%Y%m%d-%H%M%S}-{rpt_id:05d}"

#     # ---------- GET branch unchanged ----------
#     if request.method == "GET":
#         with connection.cursor() as cur:
#             cur.execute(
#                 """
#                 SELECT br.blotter_report_id,
#                        COALESCE(br.incident_subject,'(no subject)') AS subj,
#                        to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
#                        COALESCE(br.incident_desc,'') AS desc
#                   FROM blotter_report br
#                  WHERE br.blotter_report_id = %s
#                 """,
#                 [report_id],
#             )
#             rpt = cur.fetchone()
#             if not rpt:
#                 return HttpResponseBadRequest("Report not found.")

#             cur.execute(
#                 """
#                 SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')) AS name, 'COMPLAINANT' AS role
#                   FROM complainant_report cr
#                   JOIN person p ON p.person_id = cr.person_id
#                  WHERE cr.blotter_report_id = %s
#                 UNION ALL
#                 SELECT p.person_id, trim(coalesce(p.first_name,'') || ' ' || coalesce(p.last_name,'')), 'RESPONDENT'
#                   FROM respondent_report rr
#                   JOIN person p ON p.person_id = rr.person_id
#                  WHERE rr.blotter_report_id = %s
#                  ORDER BY role, name
#                 """,
#                 [report_id, report_id],
#             )
#             parties = cur.fetchall()

#             cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
#             complaint_titles = cur.fetchall()
#             cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
#             case_natures = cur.fetchall()
#             cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
#             settlements = cur.fetchall()
#             cur.execute("SELECT payment_status_name FROM payment_status ORDER BY 1")
#             payment_statuses = [r[0] for r in cur.fetchall()]

#         ctx = {
#             "page_title": "Confirm Payment & Open Case",
#             "report": rpt,
#             "parties": parties,
#             "complaint_titles": complaint_titles,
#             "case_natures": case_natures,
#             "settlement_statuses": settlements,
#             "payment_statuses": payment_statuses,
#             "default_or": _make_default_or(report_id),  # shown in the UI
#             "default_amount": "150.00",
#         }
#         return render(request, "lupon_mem/report_pay.html", ctx)

#     # ---------- POST branch (updated) ----------
#     auth = request.session.get("auth") or {}
#     staff_id = auth.get("staff_id")

#     # required case fields
#     case_name            = (request.POST.get("case_name") or "").strip() or "Untitled Case"
#     complaint_title_id   = _toi(request.POST.get("complaint_title_id"))
#     case_nature_id       = _toi(request.POST.get("case_nature_id"))
#     settlement_status_id = _toi(request.POST.get("settlement_status_id"))

#     # payment toggle + details
#     with_payment        = (request.POST.get("with_payment") == "on")
#     payment_receipt     = (request.POST.get("payment_receipt") or "").strip()
#     payment_amount      = _to_decimal(request.POST.get("payment_amount"), default="0")
#     payment_status      = (request.POST.get("payment_status") or "PAID").strip()
#     paid_by_person_id   = _toi(request.POST.get("paid_by_person_id"))

#     # If the checkbox is ON, but receipt is blank -> auto-generate and force PAID (unless explicitly overridden)
#     if with_payment:
#         if not payment_receipt:
#             payment_receipt = _make_default_or(report_id)
#         if not payment_status:
#             payment_status = "PAID"
#         # keep amount as parsed (0 if empty); caller may set a default in UI

#     # If the checkbox is OFF -> do not send any payment at all
#     if not with_payment:
#         payment_receipt = None
#         payment_amount = None
#         payment_status = "UNPAID"
#         paid_by_person_id = None

#     args = [
#         report_id,
#         case_name,
#         complaint_title_id,
#         case_nature_id,
#         settlement_status_id,
#         staff_id,

#         # payment group
#         with_payment,
#         payment_receipt,
#         payment_amount,
#         payment_status,
#         paid_by_person_id,

#         # status after
#         "FOR CASE FILING",
#         "Report converted to case",
#     ]

#     with connection.cursor() as cur:
#         cur.execute(
#             """SELECT confirm_report_and_open_case(
#                 %s,%s,%s,%s,%s,%s,
#                 %s,%s,%s,%s,%s,
#                 %s,%s
#             )""",
#             args,
#         )
#         case_id = cur.fetchone()[0]

#     messages.success(request, f"Case #{case_id} created.")
#     return redirect("lupon_mem:case_detail", case_id=case_id)




# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}
LUPON_ROLES_LIST = ["BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"]  # pass to templates

from django.views.decorators.http import require_POST

# ------------------------------
# REPORT LIST
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def report_list(request: HttpRequest):
    q_raw = (request.GET.get("q") or "").strip()
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip()

    with connection.cursor() as cur:
        base_sql = """
            SELECT
              br.blotter_report_id,                               -- 0
              COALESCE(br.incident_subject,'(no subject)'),       -- 1
              to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at, -- 2
              ps.payment_status_name                               -- 3
            FROM blotter_report br
            LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
        """
        if q_raw:
            cur.execute(
                base_sql + " WHERE br.incident_subject ILIKE CONCAT('%', %s, '%') ORDER BY br.date_time_reported DESC LIMIT 200",
                [q_raw],
            )
        else:
            cur.execute(base_sql + " ORDER BY br.date_time_reported DESC LIMIT 200")
        rows = cur.fetchall()

    return render(
        request,
        "lupon_mem/report_list.html",
        {
            "rows": rows,
            "q": q_raw,
            "user_role": user_role,
            "LUPON_ROLES_LIST": LUPON_ROLES_LIST,
        },
    )


# ------------------------------
# REVIEW (Lupon) – no Payment card; Approve/Decline here
# ------------------------------
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def report_review(request: HttpRequest, report_id: int):
    auth = request.session.get("auth") or {}
    role = (auth.get("role_name") or auth.get("role") or "").strip()

    with connection.cursor() as cur:
        cur.execute("""
            SELECT br.blotter_report_id,
                   COALESCE(br.incident_subject,'(no subject)') AS subj,
                   COALESCE(br.incident_desc,'') AS descr,
                   to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at,
                   COALESCE(ps.payment_status_name, '—') AS pay_status,
                   /* ---- appended: incident address text ---- */
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

        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY 2")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY 2")
        case_natures = cur.fetchall()
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY 2")
        settlements = cur.fetchall()

    ctx = {
        "page_title": "Approve Blotter Report",
        "report": rpt,
        "parties": parties,
        "complaint_titles": complaint_titles,
        "case_natures": case_natures,
        "settlement_statuses": settlements,
        "user_role": role,
        "LUPON_ROLES_LIST": LUPON_ROLES_LIST,
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

    # DEBUG: show decline payload
    print("\n[DEBUG][DECLINE] report_id=", report_id, " staff_id=", staff_id, " reason=", reason)

    with connection.cursor() as cur:
        try:
            print("[DEBUG][DECLINE] SQL → decline_report_request(%s,%s,%s)")
            cur.execute("SELECT decline_report_request(%s,%s,%s)", [report_id, staff_id, reason])
            res = cur.fetchone()
            print("[DEBUG][DECLINE] DB result:", res)
        except Exception as e:
            print("[DEBUG][DECLINE] fallback UPDATE path due to:", e)
            try:
                print("[DEBUG][DECLINE] SQL → UPDATE blotter_report ... set status = 'DECLINED'")
                cur.execute("""
                    UPDATE blotter_report
                       SET remarks = CONCAT(COALESCE(remarks,''), CASE WHEN remarks<>'' THEN E'\n' ELSE '' END, %s),
                           status  = 'DECLINED'
                     WHERE blotter_report_id=%s
                """, [f"[DECLINED] {reason}", report_id])
            except Exception as e2:
                print("[DEBUG][DECLINE] secondary fallback (no status column?)", e2)
                cur.execute("""
                    UPDATE blotter_report
                       SET remarks = CONCAT(COALESCE(remarks,''), CASE WHEN remarks<>'' THEN E'\n' ELSE '' END, %s)
                     WHERE blotter_report_id=%s
                """, [f"[DECLINED] {reason}", report_id])

    messages.success(request, f"Report #{report_id} declined.")
    return redirect("lupon_mem:report_review", report_id=report_id)

# ------------------------------
# TREASURER: PAY & OPEN CASE
# ------------------------------
# lupon_mem/views.py

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
