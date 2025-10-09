from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional

from django.shortcuts import render, redirect
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    HttpResponseNotFound,
)
from django.contrib import messages
from django.db import connection, transaction
from django.urls import reverse
from django.conf import settings

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

from lupon_mem.services.form_renderer import render_preview_png, render_final_pdf
from django.core.exceptions import ValidationError
from lupon_mem.constants import KP_FORMS_CATALOG   # static chooser catalog

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


# --- list cases (with safe search) ---
@session_login_required
@role_required(*LUPON_ROLES)
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
@role_required(*LUPON_ROLES)
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
              COALESCE(cn.case_name,'—') AS nature_name            -- 6
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn ON cn.case_nature_id = bc.case_nature_id
           WHERE bc.blotter_case_id=%s
        """,
            [case_id],
        )
        case = cur.fetchone()

        cur.execute(
            """
          SELECT
              s.submission_id,                                     -- 0
              kf.form_code,                                        -- 1
              kf.form_name,                                        -- 2
              s.status,                                            -- 3
              CASE
                WHEN s.submitted_at IS NULL THEN '—'
                ELSE to_char(s.submitted_at,'Mon DD, YYYY HH12:MI AM')
              END AS submitted_fmt                                 -- 4
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
           WHERE s.blotter_case_id=%s
           ORDER BY (s.submitted_at IS NULL), s.submitted_at DESC, s.submission_id DESC
        """,
            [case_id],
        )
        forms = cur.fetchall()

    return render(
        request,
        "lupon_mem/case_detail.html",
        {"case": case, "forms": forms, "case_id": case_id},
    )


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
    """
    from datetime import date as _date, datetime as _dt

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

        # Resolve address: prefer bc.incident_location; else from report → addresss + purok_sitio
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
        src_date = date_filed or incident_date or _date.today()  # used for KP-7 etc.
        try:
            if isinstance(src_date, str):
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        src_date = _dt.strptime(src_date, fmt).date()
                        break
                    except Exception:
                        pass
            if not hasattr(src_date, "year"):
                src_date = _date.today()
        except Exception:
            src_date = _date.today()

        date_created_iso = _iso_date(src_date) or _date.today().isoformat()
        month_created    = src_date.strftime("%B")
        year_received    = str(src_date.year)
        month_received   = month_created

        # --- TODAY (KP-9 "current" stamps) ---
        today = _date.today()
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

    # KP-9 page 2 split
    page2_index = None
    for idx, (_kff, _fid, _lbl, _typ, _req, _val, code) in enumerate(fields_with_values, start=1):
        if (code or "").strip().lower() == "served_to":
            page2_index = idx
            break

    # NEW: show only until a specific field_code
    stop_code = request.GET.get("show_until")
    # default for KP-7 is up to 'solutions_seeked'
    if not stop_code and str(fid) == "7":
        stop_code = "solutions_seeked"
    if stop_code:
        fields_with_values = _slice_until_code(fields_with_values, stop_code)

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
@role_required(*LUPON_ROLES)
@session_login_required
def submit_form(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    import json as _json

    data = _json.loads(request.body.decode())
    submission_id = int(data["submission_id"])
    case_id = int(data["case_id"])

    try:
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception:
        return JsonResponse(
            {"ok": False, "error": "Failed to generate PDF."}, status=500
        )

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
                signed = supabase.storage.from_(bucket).create_signed_url(
                    path, 60 * 60 * 24 * 7
                )
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

    with connection.cursor() as cur:
        cur.execute(
            "UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s",
            [submission_id],
        )

    local_download = request.build_absolute_uri(
        reverse("lupon_mem:submission_pdf", args=[submission_id])
    )

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
@role_required(*LUPON_ROLES)
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


@session_login_required
@role_required(*LUPON_ROLES)
def report_list(request: HttpRequest):
    q_raw = (request.GET.get("q") or "").strip()

    with connection.cursor() as cur:
        if q_raw:
            cur.execute(
                """
                SELECT br.blotter_report_id,
                       br.incident_subject,
                       to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at
                  FROM blotter_report br
                 WHERE br.incident_subject ILIKE CONCAT('%', %s, '%')
                 ORDER BY br.date_time_reported DESC
                 LIMIT 200
            """,
                [q_raw],
            )
        else:
            cur.execute(
                """
                SELECT br.blotter_report_id,
                       br.incident_subject,
                       to_char(br.date_time_reported,'YYYY-MM-DD HH24:MI') AS reported_at
                  FROM blotter_report br
                 ORDER BY br.date_time_reported DESC
                 LIMIT 200
            """
            )

        rows = cur.fetchall()

    return render(request, "lupon_mem/report_list.html", {"rows": rows, "q": q_raw})


@session_login_required
@role_required(*LUPON_ROLES)
def report_new(request: HttpRequest):
    if request.method == "GET":
        return render(request, "lupon_mem/report_new.html", {"page_title": "New Report"})

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    complainant_id = _toi(request.POST.get("complainant_id"))
    respondent_ids = [_toi(x) for x in (request.POST.get("respondent_ids") or "").split(",")]
    respondent_ids = [x for x in respondent_ids if x]

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
                _toi(request.POST.get("incident_address_id")),
                complainant_id,
                respondent_ids if respondent_ids else None,
                None,  # evidence jsonb
            ],
        )
        report_id = cur.fetchone()[0]

    messages.success(request, f"Report #{report_id} filed.")
    return redirect("lupon_mem:report_list")


@session_login_required
@role_required(*LUPON_ROLES)
def report_confirm(request: HttpRequest, report_id: int):
    if request.method == "GET":
        with connection.cursor() as cur:
            cur.execute(
                """
              SELECT br.blotter_report_id, br.incident_subject, br.incident_desc,
                     br.incident_date, br.incident_time
              FROM blotter_report br WHERE br.blotter_report_id=%s
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

        ctx = {
            "rpt": rpt,
            "parties": parties,
            "complaint_titles": complaint_titles,
            "case_natures": case_natures,
            "settlement_statuses": settlements,
            "report_id": report_id,
            "page_title": "Confirm & Open Case",
        }
        return render(request, "lupon_mem/report_confirm.html", ctx)

    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")

    with_payment = (request.POST.get("with_payment") == "on")
    args = [
        report_id,
        request.POST.get("case_name") or "Untitled Case",
        _toi(request.POST.get("complaint_title_id")),
        _toi(request.POST.get("case_nature_id")),
        _toi(request.POST.get("settlement_status_id")),
        staff_id,
        with_payment,
        request.POST.get("payment_receipt") or None,
        request.POST.get("payment_amount") or None,
        (request.POST.get("payment_status") or "PAID"),
        _toi(request.POST.get("paid_by_person_id")),
    ]
    with connection.cursor() as cur:
        cur.execute(
            """SELECT confirm_report_and_open_case(
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )""",
            args,
        )
        case_id = cur.fetchone()[0]

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
@role_required(*LUPON_ROLES)
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
