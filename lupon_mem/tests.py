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

# caching / logging
from django.core.cache import cache
import time, logging
log = logging.getLogger(__name__)

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}


# -----------------------------
# helper: slice fields by code
# -----------------------------

# helper: get a dict of submitted KP codes for this case (True if there's a SUBMITTED one)
# --- helper: latest submitted submission for any of the given form codes
# --- Auto-generate MEDx Settled Case Summary after KP-16 submit ---
def _ordinal(n: int) -> str:
    if n % 100 in (11, 12, 13):
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"



def _list_mediation_photos(case_id: int, submission_id: int | None):
    """
    Return dicts the template can render. We avoid selecting a PK column
    because your environments disagree on its name ('id' vs 'media_id' vs none).
    """
    rows = []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              file_path,
              mime_type,
              uploaded_at
            FROM case_hearing_media
            WHERE blotter_case_id = %s
              AND media_kind = 'PHOTO'
              AND (%s IS NULL OR submission_id = %s)
            ORDER BY uploaded_at DESC
        """, [case_id, submission_id, submission_id])

        for file_path, mime_type, uploaded_at in cur.fetchall():
            path = file_path or ""
            # If already a full URL (Supabase public), use it as-is.
            if path.startswith("http://") or path.startswith("https://"):
                display_url = path
            else:
                # Legacy/local storage path under MEDIA_URL
                from django.conf import settings
                media_url = getattr(settings, "MEDIA_URL", "/media/")
                if not media_url.endswith("/"):
                    media_url += "/"
                display_url = media_url + path.lstrip("/")

            rows.append({
                # no 'id' field needed by the template
                "file_path": path,
                "display_url": display_url,
                "mime_type": mime_type,
                "uploaded_at": uploaded_at,
            })
    return rows






def _has_mediation_attendance(case_id: int) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
            LIMIT 1
        """, [case_id])
        return cur.fetchone() is not None




def _open_kp16_draft(case_id: int) -> int:
    """
    Create (or reuse) a KP-16 DRAFT with minimal prefill and return submission_id.
    Does NOT submit; just prepares the form so the Lupon can type the settlement statement.
    """
    with connection.cursor() as cur:
        # Reuse most recent KP-16 DRAFT if present
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='KP-16'
              AND UPPER(s.status)='DRAFT'
            ORDER BY s.submission_id DESC
            LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        if r:
            return int(r[0])

        # Create new DRAFT
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-16' AND is_active IS TRUE LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise ValidationError("KP-16 is not configured/active.")
        form_id = int(row[0])

        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT') RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # Prefill some friendly defaults (optional)
        pre = _prefill_minimal_for_case(case_id)
        cur.execute("""
            SELECT kff.field_id, LOWER(kf.field_code)
            FROM kp_form_field kff
            JOIN kp_field kf ON kf.field_id = kff.field_id
            WHERE kff.form_id=%s
        """, [form_id])
        import json as _json
        for field_id, code in cur.fetchall():
            v = pre.get((code or "").lower())
            if v in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id)
                DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(v)])

        return sid






def _latest_notice_submitted_at(case_id: int):
    """Newest submitted_at among KP-8 / KP-12 for this case, or None."""
    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code) IN ('KP-8','KP-12')
            )
            SELECT MAX(s.submitted_at)
            FROM blotter_kp_submission s
            WHERE s.blotter_case_id=%s
              AND s.form_id IN (SELECT form_id FROM forms)
              AND UPPER(s.status)='SUBMITTED'
        """, [case_id])
        row = cur.fetchone()
    return row[0] if row else None


def _is_hearing_held(case_id: int, *, strict: bool = True) -> bool:
    """
    strict=True  -> require HELD date_processed > latest KP-8/12 submitted_at
    strict=False -> any HELD (HEARING HELD / CONCILIATION HELD) on the case is enough
    """
    latest_notice_at = _latest_notice_submitted_at(case_id)

    with connection.cursor() as cur:
        if strict and latest_notice_at:
            cur.execute("""
                SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t
                    ON t.case_progress_type_id=cpt.case_progress_type_id
                 WHERE cpt.blotter_case_id=%s
                   AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                   AND cpt.date_processed > %s
                 LIMIT 1
            """, [case_id, latest_notice_at])
        else:
            # relaxed: any HELD is enough (used in dev/testing)
            cur.execute("""
                SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t
                    ON t.case_progress_type_id=cpt.case_progress_type_id
                 WHERE cpt.blotter_case_id=%s
                   AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                 LIMIT 1
            """, [case_id])
        r = cur.fetchone()
    return bool(r)


# helpers v2.9
# --- Count and list MED-ATT (case-level; oldest → newest)



def _count_med_att_case(case_id: int) -> int:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
        """, [case_id])
        return int(cur.fetchone()[0] or 0)



def _list_med_att_case(case_id: int) -> list[int]:
    """Return submission_ids of submitted MED-ATT-2025 (oldest→newest)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)='MED-ATT-2025'
              AND UPPER(s.status)='SUBMITTED'
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
        """, [case_id])
        return [int(r[0]) for r in cur.fetchall()]





def _get_form_id(form_code: str) -> int | None:
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)=UPPER(%s) LIMIT 1", [form_code])
        row = cur.fetchone()
    return row[0] if row else None


def _has_med_attendance(case_id: int) -> bool:
    """
    True if the case has at least one submitted 'MED-ATT-2025' form.
    (Status can be DRAFT or SUBMITTED — loosen as you prefer.)
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
              AND UPPER(f.form_code) = 'MED-ATT-2025'
            LIMIT 1
        """, [case_id])
        return cur.fetchone() is not None



def _list_case_photos(case_id: int):
    """Return recent PHOTO attachments (for UI gallery)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_hearing_media_id, file_path, caption, uploaded_at
            FROM case_hearing_media
            WHERE blotter_case_id = %s
              AND is_deleted = FALSE
              AND media_kind = 'PHOTO'
            ORDER BY uploaded_at DESC, case_hearing_media_id DESC
            LIMIT 60
        """, [case_id])
        rows = cur.fetchall()
    return [
        {"id": r[0], "file_path": r[1], "caption": r[2], "uploaded_at": r[3]}
        for r in rows
    ]




def _latest_submission_for_codes(case_id: int, codes: list[str]):
    codes_up = [c.upper() for c in codes]
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id, UPPER(f.form_code) AS code, s.submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
              AND UPPER(f.form_code) = ANY(%s)
              AND UPPER(s.status) = 'SUBMITTED'
            ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 1
        """, [case_id, codes_up])
        return cur.fetchone()   # (submission_id, code, submitted_at) or None

# --- new: open/download the latest settlement summary (KP-16)
# lupon_mem/views.py

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_summary_pdf(request, case_id: int):
    """
    Download the Barangay Case Summary.
    Prefer MEDx-SETTLED (MED1/MED2/MED3) over KP-16.
    If none exists yet:
      - If LUPON_AUTOGEN_MEDX=True, auto-generate MEDx from KP-16 and return it.
      - If LUPON_AUTOGEN_MEDX=False, just show the KP-16 PDF.
    """
    # 1) Prefer an existing MEDx summary, newest first
    med_codes = ["MED3-SETTLED", "MED2-SETTLED", "MED1-SETTLED"]
    row = _latest_submission_for_codes(case_id, med_codes)

    if row:
        submission_id, code, _ = row
        # Debug: show which summary we picked
        print(f"[CASE SUMMARY] Using existing {code} submission_id={submission_id} for case_id={case_id}")
        return redirect(f"/lupon_mem/api/submissions/{submission_id}/pdf/")

    # 2) No MEDx yet — do we have a submitted KP-16 that we can summarize OR show?
    kp16 = _latest_submission_for_codes(case_id, ["KP-16"])
    if kp16:
        kp16_submission_id, _, _ = kp16

        # Respect feature flag:
        # - True  -> keep old behavior: auto-generate MEDx and redirect to it
        # - False -> show KP-16 PDF directly (no MEDx generation)
        if getattr(settings, "LUPON_AUTOGEN_MEDX", False):
            print(
                f"[CASE SUMMARY] No MEDx yet; KP-16 found (submission_id={kp16_submission_id}). "
                f"Auto-generating MEDx summary…"
            )
            try:
                generated = _autogen_settled_summary(
                    case_id=case_id,
                    kp16_submission_id=kp16_submission_id
                ) or []
            except Exception as e:
                print("[CASE SUMMARY][ERROR] _autogen_settled_summary failed:", e)
                messages.error(request, "Failed to build the case summary from KP-16.")
                return redirect("lupon_mem:case_detail", case_id=case_id)

            # Prefer MED3 > MED2 > MED1 if multiple were generated
            med_by_code = {item.get("code"): item for item in generated if isinstance(item, dict)}
            for code in med_codes:
                if code in med_by_code:
                    sid = med_by_code[code].get("submission_id")
                    if sid:
                        print(f"[CASE SUMMARY] Generated {code} submission_id={sid}; redirecting to PDF…")
                        return redirect(f"/lupon_mem/api/submissions/{sid}/pdf/")

            # Fallback for tuple-style returns
            for item in generated:
                try:
                    sid = int(item[0])
                    code = str(item[1]).upper()
                    if code.startswith("MED") and "SETTLED" in code:
                        print(f"[CASE SUMMARY] Generated {code} submission_id={sid}; redirecting to PDF…")
                        return redirect(f"/lupon_mem/api/submissions/{sid}/pdf/")
                except Exception:
                    pass

            messages.error(request, "Summary was created but no downloadable file was found.")
            return redirect("lupon_mem:case_detail", case_id=case_id)
        else:
            # NEW behavior when auto-gen is OFF: show the KP-16 PDF instead
            print(
                f"[CASE SUMMARY] LUPON_AUTOGEN_MEDX is OFF. "
                f"Showing KP-16 submission_id={kp16_submission_id} for case_id={case_id}"
            )
            messages.info(request, "Showing KP-16 (no MED summary is auto-generated).")
            return redirect(f"/lupon_mem/api/submissions/{kp16_submission_id}/pdf/")

    # 3) Nothing to show
    messages.warning(request, "No settlement summary found. Submit KP-16 first to generate the summary.")
    return redirect("lupon_mem:case_detail", case_id=case_id)


def _submitted_codes(case_id: int) -> dict[str, bool]:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT UPPER(f.form_code) AS code, BOOL_OR(UPPER(s.status)='SUBMITTED') AS is_submitted
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
            GROUP BY 1
        """, [case_id])
        return {row[0]: bool(row[1]) for row in cur.fetchall()}

def _hearings_held(case_id: int) -> int:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) 
            FROM case_progress_tracking cpt
            JOIN case_progress_type t 
              ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id = %s
              AND UPPER(t.case_progress_type_name) = 'HEARING HELD'
        """, [case_id])
        return int(cur.fetchone()[0])

def _current_settlement(case_id: int) -> str:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(UPPER(ss.settlement_status_name), 'NOT SETTLED')
            FROM blotter_case bc
            LEFT JOIN settlement_status ss 
              ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        row = cur.fetchone()
        return row[0] if row else 'NOT SETTLED'


def _hearing_gate(case_id: int) -> dict:
    """
    Computes hearing/conciliation gate for a case.

    Returns:
      {
        'hearings_held': int,
        'latest_notice_submitted_at': datetime|None,
        'latest_notice_submission_id': int|None,
        'latest_notice_outstanding': bool,   # True if a KP-8/12 exists and no HELD after it
        'settlement_name': str|None,
        'can_issue_notice': bool,
        'reason': str,                       # why issuance is blocked
        'limit_reached': bool,               # 3 held already
      }
    """
    with connection.cursor() as cur:
        cur.execute("""
            WITH f8 AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-8'  LIMIT 1),
                 f12 AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-12' LIMIT 1),

            latest AS (
              SELECT s.submission_id, s.submitted_at
              FROM blotter_kp_submission s
              WHERE s.blotter_case_id=%s
                AND s.form_id IN ( (SELECT form_id FROM f8), (SELECT form_id FROM f12) )
              ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                       s.submitted_at DESC NULLS LAST,
                       s.submission_id DESC
              LIMIT 1
            ),

            held AS (
              SELECT COUNT(*)::int AS c,
                     COALESCE(MAX(cpt.date_processed), TIMESTAMP '0001-01-01') AS last_held_at
              FROM case_progress_tracking cpt
              JOIN case_progress_type t
                ON t.case_progress_type_id=cpt.case_progress_type_id
              WHERE cpt.blotter_case_id=%s
                AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
            ),

            st AS (
              SELECT COALESCE(ss.settlement_status_name,'PENDING') AS name
              FROM blotter_case bc
              LEFT JOIN settlement_status ss ON ss.settlement_status_id=bc.settlement_status_id
              WHERE bc.blotter_case_id=%s
            )

            SELECT
              (SELECT c FROM held)                             AS hearings_held,
              (SELECT submitted_at FROM latest)                AS latest_submitted_at,
              (SELECT submission_id FROM latest)               AS latest_sid,
              (SELECT name FROM st)                            AS settlement_name,
              (SELECT last_held_at FROM held)                  AS last_held_at
        """, [case_id, case_id, case_id])
        r = cur.fetchone()

    hearings_held, latest_at, latest_sid, settlement_name, last_held_at = r
    # outstanding if there is a latest notice and no HELD logged AFTER that notice
    latest_outstanding = bool(latest_at and (not last_held_at or last_held_at <= latest_at))

    settlement_up = (settlement_name or '').strip().upper()
    settlement_pending = settlement_up in ('PENDING', 'NOT SETTLED', 'UNSET', 'FOR MEDIATION', 'FOR CONCILIATION')

    limit_reached = hearings_held >= 3

    can_issue = (not limit_reached) and (not latest_outstanding) and settlement_pending

    reason = ""
    if limit_reached:
        reason = "Limit reached: 3 hearings already held (proceed to Arbitration/CFA)."
    elif latest_outstanding:
        reason = "There is an upcoming hearing from the latest KP-8/12 (mark it HELD first)."
    elif not settlement_pending:
        reason = f"Settlement is “{settlement_name}” (change to Pending/Not Settled to schedule another)."

    return {
        "hearings_held": hearings_held or 0,
        "latest_notice_submitted_at": latest_at,
        "latest_notice_submission_id": latest_sid,
        "latest_notice_outstanding": latest_outstanding,
        "settlement_name": settlement_name,
        "can_issue_notice": bool(can_issue),
        "reason": reason,
        "limit_reached": bool(limit_reached),
    }

from typing import Dict
from datetime import date as _date
from django.db import connection



def _create_and_submit_form_from_prefill(case_id: int, form_code: str, prefill: dict[str, object] | None = None) -> Optional[int]:
    """
    Creates a blotter_kp_submission for `form_code`, writes answers using the provided
    `prefill` map keyed by *field_code*, marks SUBMITTED, and returns submission_id.
    Returns None if form_code not active/doesn't exist.
    """
    form_code_up = (form_code or "").strip().upper()
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)=%s AND is_active IS TRUE LIMIT 1", [form_code_up])
        r = cur.fetchone()
        if not r:
            return None
        form_id = int(r[0])

        # create submission (DRAFT)
        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT') RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # gather fields for this form
        cur.execute("""
            SELECT f.field_id, LOWER(f.field_code) AS code
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id=%s
        """, [form_id])
        fields = cur.fetchall()

        # pick values for each field from prefill (skip None/blank to keep PDFs tidy)
        import json as _json
        pmap = (prefill or {})
        for field_id, code in fields:
            code = (code or "").lower()
            if code in pmap:
                val = pmap[code]
            else:
                continue
            if val in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id) DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(val)])

        # mark SUBMITTED
        cur.execute("UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s", [sid])

    return sid




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
            # ✅ include more common column names
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='person'
                  AND column_name IN (
                    'mobile_number','mobile','mobile_no','mobile_num',
                    'phone','contact_no','contact_number','contact',
                    'cellphone','cell_no','cellphone_no'
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
from urllib.parse import urlencode

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_list(request: HttpRequest):
    """
    Live-searchable case list with filters, themed pagination, and partial rendering.
    - GET params:
        q, type_id, nature_id, settlement_id, filed_from (YYYY-MM-DD), filed_to (YYYY-MM-DD),
        page (int), per_page (int; default 10), partial=1 for partial render
    """
    q = (request.GET.get("q") or "").strip()
    type_id = (request.GET.get("type_id") or "").strip()          # complaint_title_id
    nature_id = (request.GET.get("nature_id") or "").strip()      # case_nature_id
    settlement_id = (request.GET.get("settlement_id") or "").strip()
    filed_from = (request.GET.get("filed_from") or "").strip()
    filed_to = (request.GET.get("filed_to") or "").strip()

    # pagination params
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    try:
        per_page = max(int(request.GET.get("per_page", "10")), 1)
    except ValueError:
        per_page = 10
    offset = (page - 1) * per_page

    # ---------- choices for filters ----------
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name ASC")
        type_choices = cur.fetchall()  # [(id, name), ...]
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name ASC")
        nature_choices = cur.fetchall()
        # settlement status list (if this table exists in your schema)
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name ASC")
        settlement_choices = cur.fetchall()

    # ---------- base query parts ----------
    base_from = """
        FROM blotter_case bc
        LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
        LEFT JOIN case_nature cn      ON cn.case_nature_id      = bc.case_nature_id
        LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
    """

    where_parts = []
    params: list = []

    if q:
        where_parts.append("""
            (
                bc.blotter_case_num  ILIKE CONCAT('%%', %s, '%%')
             OR bc.blotter_case_name ILIKE CONCAT('%%', %s, '%%')
             OR bc.incident_desc     ILIKE CONCAT('%%', %s, '%%')
            )
        """)
        params.extend([q, q, q])

    if type_id:
        where_parts.append("bc.complaint_title_id = %s")
        params.append(type_id)

    if nature_id:
        where_parts.append("bc.case_nature_id = %s")
        params.append(nature_id)

    if settlement_id:
        where_parts.append("bc.settlement_status_id = %s")
        params.append(settlement_id)

    if filed_from:
        where_parts.append("bc.date_filed >= %s")
        params.append(filed_from)

    if filed_to:
        where_parts.append("bc.date_filed <= %s")
        params.append(filed_to)

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # ---------- total count ----------
    with connection.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) {base_from} {where_sql}", params)
        total = cur.fetchone()[0]

    # ---------- page rows ----------
    with connection.cursor() as cur:
        select_sql = f"""
            SELECT
                bc.blotter_case_id,                      -- 0
                bc.blotter_case_num,                     -- 1
                bc.blotter_case_name,                    -- 2
                to_char(bc.date_filed,'Mon DD, YYYY') AS date_filed_fmt,  -- 3
                COALESCE(ct.complaint_title_name,'—') AS complaint_title, -- 4
                COALESCE(cn.case_name,'—')             AS case_nature,    -- 5
                COALESCE(ss.settlement_status_name,'—') AS settlement_status -- 6
            {base_from}
            {where_sql}
            ORDER BY bc.blotter_case_id DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(select_sql, params + [per_page, offset])
        rows = cur.fetchall()

    # ---------- pagination helpers ----------
    total_pages = max((total + per_page - 1) // per_page, 1)
    has_prev = page > 1
    has_next = page < total_pages
    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))

    # preserve current filters for link building (except 'page')
    preserved = {
        "q": q,
        "type_id": type_id,
        "nature_id": nature_id,
        "settlement_id": settlement_id,
        "filed_from": filed_from,
        "filed_to": filed_to,
        "per_page": per_page,
    }
    # remove empty keys
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
        "type_id": type_id,
        "nature_id": nature_id,
        "settlement_id": settlement_id,
        "filed_from": filed_from,
        "filed_to": filed_to,
        "type_choices": type_choices,
        "nature_choices": nature_choices,
        "settlement_choices": settlement_choices,
    }

    # Partial render (for AJAX/live updates)
    if request.GET.get("partial") == "1":
        return render(request, "lupon_mem/partials/case_table.html", ctx)

    return render(request, "lupon_mem/case_list.html", ctx)



# --- case detail ---
# lupon_mem/views.py  (replace your case_detail with this version)

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

        # ----- Attached forms (basic list)
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

        # ----- NEW: count of KP-9 submissions WITHOUT attendance (covers 2nd/3rd unmarked)
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

        # ----- Sequence labels for KP-8 / KP-12 / KP-9 / MED-ATT-2025 (oldest→newest)
        cur.execute(
            """
            SELECT s.submission_id,
                   UPPER(kf.form_code) AS code,
                   s.submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(kf.form_code) IN ('KP-8','KP-12','KP-9','MED-ATT-2025')
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
            """,
            [case_id],
        )
        seq_rows = cur.fetchall()

    # ----- build sequence labels
    form_seq_labels: dict[int, str] = {}
    counters = {"KP-8": 0, "KP-12": 0, "KP-9": 0, "MED-ATT-2025": 0}
    for sid, code, _submitted_at in seq_rows:
        code = (code or "").upper()
        if code in counters:
            counters[code] += 1
            n = counters[code]
            if code == "KP-9":
                form_seq_labels[int(sid)] = f"{_ordinal(n)} Summons"
            elif code in ("KP-8", "KP-12"):
                form_seq_labels[int(sid)] = f"{_ordinal(n)} Hearing"
            elif code == "MED-ATT-2025":
                form_seq_labels[int(sid)] = f"{_ordinal(n)} Med Attendance"

    gate = _hearing_gate(case_id)
    hearings_count = int(gate.get("hearings_held") or 0)
    latest_notice_dt = gate.get("latest_notice_submitted_at")
    latest_hearing_dt = _fmt_dt(latest_notice_dt)

    # annotate forms
    forms = [(*row, form_seq_labels.get(int(row[0]))) for row in forms_raw]

    # ----- NEW blocking logic for Add Form (summons)
    # Finalized statuses for single attendance rows
    finalized_attendance = {"ATTENDED", "NO SHOW"}

    # OLD: latest-only
    # block_due_to_summons = bool(kp9_count and (kp9_latest_status not in finalized_attendance))
    # NEW: block if ANY KP-9 has no attendance row
    block_due_to_summons = kp9_pending_count > 0
    if block_due_to_summons:
        # Optional: keep latest-status nuance if there are zero attendance rows at all
        if kp9_count and (kp9_latest_status not in finalized_attendance):
            pass  # covered by pending count anyway

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
    # after you compute gate etc.
    med_row = _latest_submission_for_codes(case_id, ["MED1-SETTLED","MED2-SETTLED","MED3-SETTLED"])
    has_med_summary = bool(med_row)
    med_summary_sid = int(med_row[0]) if med_row else None

    context = {
        "case": case,
        "forms": forms,
        "case_id": case_id,
        "settlement_choices": settlement_choices,
        "hearing_gate": gate,

        "incident_description": case[4] if case else None,
        "case_nature": case[6] if case else None,

        "hearings_count": hearings_count,
        "kp9_count": kp9_count,
        "latest_hearing_dt": latest_hearing_dt,
        "last_hearing_dt": latest_hearing_dt,
        "next_hearing_dt": None,

        "kp9_latest_status": kp9_latest_status,
        "kp9_latest_party": kp9_latest_party,

        # NEW: expose pending count (optional for badges/UI)
        "kp9_pending_count": kp9_pending_count,

        "has_hearing": hearings_count > 0,

        # modal blocking flags + reasons
        "force_open_block_modal": force_open_block_modal,
        "block_reason": block_reason,  # 'summons' | 'hearing' | None
        "block_due_to_summons": block_due_to_summons,
        "block_due_to_hearing": block_due_to_hearing,
        "block_reason_summons": block_reason_summons,
        "block_reason_hearing": block_reason_hearing,

        "has_med_summary": has_med_summary,
        "med_summary_sid": med_summary_sid,
    }

    return render(request, "lupon_mem/case_detail.html", context)


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
    gate = _hearing_gate(case_id)
    return render(
        request,
        "lupon_mem/add_form_choose.html",
        {"case_id": case_id, "forms": forms, "hearing_gate": gate}
    )


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

    if kp9_ui_minimal:
        allowed_codes = {"summon_date", "summon_time"}
        fields_with_values = [
            item for item in fields_with_values
            if ((item[6] or "").strip().lower() in allowed_codes)
        ]
        page2_index = None  # nothing to split since we only show 2 fields

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
@role_required(*LUPON_ROLES)
@session_login_required
def submit_form(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("Method not allowed")

    import json as _json
    from datetime import datetime as _dt
    log = logging.getLogger(__name__)

    # --- Parse body
    try:
        data = _json.loads(request.body.decode())
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    try:
        submission_id = int(data["submission_id"])
        case_id       = int(data["case_id"])
    except Exception:
        return JsonResponse({"ok": False, "error": "Missing or invalid submission_id/case_id."}, status=400)

    # --- Persist latest answers if provided (upsert)
    answers_payload = data.get("answers")
    if isinstance(answers_payload, dict) and answers_payload:
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    for field_id_str, value in answers_payload.items():
                        cur.execute("""
                            INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (submission_id, field_id)
                            DO UPDATE SET value_json = EXCLUDED.value_json
                        """, [submission_id, int(field_id_str), _json.dumps(value)])
        except Exception:
            log.exception("submit_form upsert answers failed (submission_id=%s)", submission_id)
            return JsonResponse({"ok": False, "error": "Failed to save answers before rendering."}, status=500)

    # --- Render PDF
    try:
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception:
        log.exception("submit_form render_final_pdf failed")
        return JsonResponse({"ok": False, "error": "Failed to generate PDF."}, status=500)

    # --- Upload to Supabase (best-effort)
    bucket = getattr(settings, "SUPABASE_BUCKET", "documents")
    path = f"blotter/{case_id}/{filename}"
    storage_url = None
    try:
        supabase.storage.from_(bucket).upload(path, pdf_bytes,
                                              {"contentType": "application/pdf", "upsert": "true"})
        try:
            pub = supabase.storage.from_(bucket).get_public_url(path)
            storage_url = pub.get("publicUrl") if isinstance(pub, dict) else (pub if isinstance(pub, str) else None)
        except Exception:
            storage_url = None
        if not storage_url:
            try:
                signed = supabase.storage.from_(bucket).create_signed_url(path, 60 * 60 * 24 * 7)
                storage_url = (signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")) \
                              if isinstance(signed, dict) else None
            except Exception:
                storage_url = None
    except Exception:
        storage_url = None

    # --- Mark SUBMITTED
    try:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE blotter_kp_submission "
                "SET status='SUBMITTED', submitted_at=now() "
                "WHERE submission_id=%s",
                [submission_id]
            )
    except Exception:
        log.exception("submit_form failed to mark SUBMITTED (submission_id=%s)", submission_id)
        return JsonResponse({"ok": False, "error": "Failed to finalize submission."}, status=500)

    # --- Determine the just-submitted form code (used multiple times below)
    row_fc = None
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(kf.form_code)
                  FROM blotter_kp_submission s
                  JOIN kp_form kf ON kf.form_id = s.form_id
                 WHERE s.submission_id=%s
            """, [submission_id])
            row_fc = cur.fetchone()
    except Exception:
        log.exception("submit_form failed to lookup form_code (submission_id=%s)", submission_id)

    # --- If this was KP-16: set CASE to SETTLED (server-of-record)
    extra_files = []
    try:
        if row_fc and str(row_fc[0]).upper() == "KP-16":
            staff_id = (request.session.get("auth") or {}).get("staff_id")
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Settled via KP-16', staff_id])
            messages.success(request, "Settlement finalized (KP-16 submitted).")
    except Exception:
        log.exception("Failed to set case SETTLED on KP-16 submit")

    # --- Auto-generate MEDx settled summary (best-effort) if KP-16
    # --- Auto-generate MEDx settled summary (feature-flagged; default OFF)
    extra_files = []
    try:
        if (
            row_fc and str(row_fc[0]).upper() == "KP-16"
            and getattr(settings, "LUPON_AUTOGEN_MEDX", False)
        ):
            extra_files = _autogen_settled_summary(case_id=case_id, kp16_submission_id=submission_id) or []
    except Exception as e:
        print("[MED-SETTLED][DEBUG] auto generation failed:", e)


    # --- NEW: Auto-mark the hearing as HELD when KP-16 came from the hearing page
    # We look for the session flag set by open_kp16_from_hearing?sid=<notice_submission_id>
    try:
        if row_fc and str(row_fc[0]).upper() == "KP-16":
            sid = request.session.get("auto_mark_hearing_after_kp16_sid")
            sid_case = request.session.get("auto_mark_hearing_case_id")
            if sid and sid_case and int(sid_case) == int(case_id):
                try:
                    with connection.cursor() as cur:
                        # If your schema/table name differs, adjust this UPDATE to match your model.
                        cur.execute("""
                            UPDATE blotter_hearing
                               SET held = TRUE,
                                   held_at = NOW()
                             WHERE blotter_case_id = %s
                               AND notice_submission_id = %s
                        """, [case_id, int(sid)])
                    messages.success(request, "Hearing automatically marked as HELD.")
                    print(f"[auto-held] case_id={case_id} notice_sid={sid} (via KP-16)")
                except Exception as e:
                    log.exception("Auto-mark hearing HELD failed (case_id=%s, sid=%s)", case_id, sid)
                    messages.warning(request, "Settlement saved, but auto-marking the hearing as HELD failed. Please mark it manually.")

                # Clear flags regardless to prevent double-fires
                request.session.pop("auto_mark_hearing_after_kp16_sid", None)
                request.session.pop("auto_mark_hearing_case_id", None)
                request.session.modified = True
    except Exception as e:
        log.exception("submit_form post-KP16 auto-held hook error: %s", e)

    # --- Local download url (always works)
    local_download = request.build_absolute_uri(reverse("lupon_mem:submission_pdf", args=[submission_id]))

    return JsonResponse({
        "ok": True,
        "file": filename,
        "download_url": local_download,
        "storage_url": storage_url,
        "extra_files": extra_files,
    })



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



from django.views.decorators.http import require_GET

@session_login_required
@role_required(*LUPON_ROLES)
@require_GET
def staff_lookup(request: HttpRequest):
    """
    JSON lookup for a single staff member.
    Input:  GET ?staff_id=123
    Output: { ok: true, result: { id, person_id, name, role, mobile } }
    """
    sid_raw = (request.GET.get("staff_id") or "").strip()
    if not sid_raw.isdigit():
        return JsonResponse({"ok": False, "error": "Invalid staff_id."}, status=400)

    staff_id = int(sid_raw)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              s.staff_id,
              p.person_id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,''))    AS name,
              coalesce(r.role_name,'')       AS role
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            LEFT JOIN rolee r ON r.role_id = s.role_id
            WHERE s.staff_id=%s
            LIMIT 1
        """, [staff_id])
        row = cur.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "Staff not found."}, status=404)

    _staff_id, person_id, name, role = row
    mobile = _get_person_mobile_number(person_id) or ""

    return JsonResponse({
        "ok": True,
        "result": {
            "id": _staff_id,
            "person_id": person_id,
            "name": (name or "").strip(),
            "role": (role or "").strip(),
            "mobile": mobile.strip()
        }
    })


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


@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest_all(request: HttpRequest):
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
            WHERE r.role_name IN (
                'BARANGAY LUPON MEMBER',
                'BARANGAY LUPON PRESIDENT',
                'BARANGAY SECRETARY',
                'BARANGAY CAPTAIN'
            )
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
# lupon_mem/views.py  (replace your add_form_choose_static with this version)

# lupon_mem/views.py  (replace your add_form_choose_static with this one)

from django.contrib import messages
from django.db import connection
from django.http import HttpRequest
from django.shortcuts import render, redirect
from django.urls import reverse

@session_login_required
@role_required(*LUPON_ROLES)
def add_form_choose_static(request, case_id: int):
    """
    Attach-a-form chooser with hard gates:
      • Block when latest KP-9 attendance not marked (unless we're adding MED-ATT-2025)
      • Block when there is an outstanding hearing notice (unless we're adding MED-ATT-2025)

    NEW: If ?code=MED-ATT-2025 (or ?from=hearing / ?allow_med_att=1) is present,
    we allow the chooser and show only MED-ATT-2025, regardless of the gates.
    """
    # ---- read intent flags from query ----
    requested_code = (request.GET.get("code") or "").upper().strip()
    allow_med_att  = (
        requested_code == "MED-ATT-2025"
        or (request.GET.get("allow_med_att") == "1")
        or (request.GET.get("from") == "hearing")
    )

    # ---- hearing gate ----
    gate = _hearing_gate(case_id)
    latest_notice_outstanding = bool(gate.get("latest_notice_outstanding"))

    # ---- latest KP-9 attendance state ----
    latest_att_status = None
    summons_count = 0
    with connection.cursor() as cur:
        cur.execute("""
            WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
            SELECT COUNT(*) FROM blotter_kp_submission
            WHERE blotter_case_id=%s AND form_id=(SELECT form_id FROM f)
        """, [case_id])
        summons_count = int(cur.fetchone()[0] or 0)

        cur.execute("""
            WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
            SELECT a.status
            FROM kp9_attendance a
            JOIN blotter_kp_submission s ON s.submission_id = a.submission_id
            WHERE s.blotter_case_id = %s
              AND s.form_id = (SELECT form_id FROM f)
            ORDER BY a.marked_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        latest_att_status = (r[0] or '').upper() if r else None

    pending_summons = (summons_count > 0) and (not latest_att_status)

    # ---- HARD GATES (bypass allowed for MED-ATT-2025 intent) ----
    if pending_summons and not allow_med_att:
        messages.warning(
            request,
            "Please mark the latest summons attendance (ATTENDED / NO SHOW) before adding a new form."
        )
        return redirect("lupon_mem:case_detail", case_id=case_id)

    if latest_notice_outstanding and not allow_med_att:
        messages.warning(
            request,
            "There is a scheduled mediation/conciliation hearing. Please record the outcome (HELD → Settled / Not Settled) first."
        )
        return redirect("lupon_mem:case_detail", case_id=case_id)

    # ---- regular phase logic (unchanged) ----
    submitted  = _submitted_codes(case_id)
    hearings   = _hearings_held(case_id)
    settle     = _current_settlement(case_id)
    is_settled = ('SETTLED' in settle) or ('AMICABLE' in settle)

    # ---- Re-read latest KP-9 details (kept for badges) ----
    latest_att_party  = None
    with connection.cursor() as cur:
        cur.execute("""
            WITH f AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1
            )
            SELECT a.status, a.no_show_party
            FROM kp9_attendance a
            JOIN blotter_kp_submission s ON s.submission_id = a.submission_id
            WHERE s.blotter_case_id = %s
              AND s.form_id = (SELECT form_id FROM f)
            ORDER BY a.marked_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        if r:
            latest_att_status = (r[0] or '').upper()
            latest_att_party  = (r[1] or '').upper() if r[1] else None

    # ---- Allowed codes decision ----
    allowed_codes: list[str] = []
    gate_msg = None
    badge_flags = {
        "summons_count": summons_count,
        "no_show_complainant": latest_att_status == 'NO SHOW' and (latest_att_party in ('COMPLAINANT','BOTH')),
        "no_show_respondent":  latest_att_status == 'NO SHOW' and (latest_att_party in ('RESPONDENT','BOTH')),
        "need_new_summons": True,   # we always allow creating another KP-9 in normal flow
    }

    # PRIORITY: if we came specifically to add MED-ATT-2025, show only that
    if allow_med_att:
        allowed_codes = ['MED-ATT-2025']
        gate_msg = "You are adding Mediation Attendance for the scheduled hearing."
    else:
        if latest_att_status == 'NO SHOW':
            if latest_att_party in ('COMPLAINANT','BOTH'):
                allowed_codes.append('KP-18')
            if latest_att_party in ('RESPONDENT','BOTH'):
                allowed_codes.append('KP-19')
            allowed_codes.append('KP-9')
            gate_msg = "Latest summons marked NO SHOW — issue the proper failure form(s) and/or a new summons."
        else:
            if not submitted.get('KP-7'):
                allowed_codes = ['KP-7']
                gate_msg = "Start mediation: issue KP-7 first."
            elif not submitted.get('KP-9'):
                allowed_codes = ['KP-9']
                gate_msg = "Next step: issue KP-9."
            elif is_settled:
                allowed_codes = []
                gate_msg = f"Case is already {settle.title()}. No new hearing forms needed."
            else:
                if hearings <= 3:
                    allowed_codes = ['KP-8', 'KP-12', 'KP-18', 'KP-19', 'KP-16', 'KP-9', 'MED-ATT-2025']
                    gate_msg = (
                        f"Hearings held {hearings}/3 — you may issue KP-8 or KP-12; "
                        "use KP-18/KP-19 for failure to appear; KP-16 when settled; MED-ATT-2025 for attendance."
                    )
                else:
                    allowed_codes = []
                    gate_msg = "Limit reached (3 hearings). Proceed to Arbitration/CFA."

    # ---- Pull form names for just the allowed codes ----
    forms: list[tuple[str, str]] = []
    if allowed_codes:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(form_code) AS code, form_name
                FROM kp_form
                WHERE UPPER(form_code) = ANY(%s)
                ORDER BY form_code
            """, [allowed_codes])
            forms = [(code, name) for code, name in cur.fetchall()]

    # ---- Optional debug logging to console ----
    print(f"[add_form_choose_static] case_id={case_id} allow_med_att={allow_med_att} requested_code={requested_code} "
          f"pending_summons={pending_summons} latest_notice_outstanding={latest_notice_outstanding} "
          f"allowed_codes={allowed_codes}")

    return render(request, "lupon_mem/add_form_choose_static.html", {
        "case_id": case_id,
        "forms": forms,
        "gate_msg": gate_msg,
        "badge_flags": badge_flags,
    })




@session_login_required
@role_required(*LUPON_ROLES)
def form_builder_by_code(request: HttpRequest, case_id: int, form_code: str):
    form_code_up = (form_code or "").strip().upper()
    if form_code_up in {"KP-8", "KP-12"}:
        gate = _hearing_gate(case_id)
        if not gate["can_issue_notice"]:
            messages.error(request, f"Cannot issue {form_code_up}. {gate['reason']}")
            return redirect("lupon_mem:case_detail", case_id=case_id)
    # resolve id then redirect as you already do
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE form_code=%s AND is_active IS TRUE", [form_code])
        row = cur.fetchone()
    if not row:
        return HttpResponseNotFound(f"Form {form_code} not found or inactive.")
    form_id = int(row[0])
    return redirect("lupon_mem:form_builder", case_id=case_id, form_id=form_id)


# --- lightweight person suggest for subpoena_to / subpoena_witness (KP-13) ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
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


# ---------- CHANGED: report_list shows payment_status ----------
# helper to read role
def _user_role(request: HttpRequest) -> str:
    auth = request.session.get("auth") or {}
    return (auth.get("role_name") or auth.get("role") or "").strip()

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




# views.py
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_hearing_list(request: HttpRequest, case_id: int):
    """
    Per-case KP-8/KP-12 notices with per-notice Held status.
    """
    from django.utils import timezone

    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (
              SELECT form_id, UPPER(form_code) AS code
              FROM kp_form
              WHERE UPPER(form_code) IN ('KP-8','KP-12')
            ),
            subs AS (
              SELECT
                s.submission_id,
                s.form_id,
                (SELECT code FROM forms f WHERE f.form_id = s.form_id) AS source_code,
                s.blotter_case_id,
                s.submitted_at
              FROM blotter_kp_submission s
              JOIN forms f ON f.form_id = s.form_id
              WHERE s.blotter_case_id = %s
            ),
            ans AS (
              SELECT
                s.submission_id,
                LOWER(kf.field_code) AS code,
                TRIM(BOTH '"' FROM a.value_json::text) AS v
              FROM subs s
              JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
              JOIN kp_field kf         ON kf.field_id      = a.field_id
              WHERE LOWER(kf.field_code) IN (
                'appearance_date','appearance_time',
                'hearing_date','hearing_time',
                'details','text box 1','venue'
              )
            ),
            pivot AS (
              SELECT
                s.submission_id,
                MAX(CASE WHEN code IN ('hearing_date','appearance_date') THEN NULLIF(v,'') END) AS hearing_date,
                MAX(CASE WHEN code IN ('hearing_time','appearance_time') THEN NULLIF(v,'') END) AS hearing_time,
                MAX(CASE WHEN code IN ('details','text box 1','venue')   THEN NULLIF(v,'') END) AS details
              FROM subs s
              LEFT JOIN ans ON ans.submission_id = s.submission_id
              GROUP BY s.submission_id
            ),
            held_per_row AS (
              SELECT
                s.submission_id,
                EXISTS(
                  SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                  WHERE cpt.blotter_case_id = %s
                    AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                    AND cpt.date_processed > s.submitted_at
                ) AS hearing_held,
                (
                  SELECT MAX(cpt.date_processed)
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                  WHERE cpt.blotter_case_id = %s
                    AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                    AND cpt.date_processed > s.submitted_at
                ) AS held_at
              FROM subs s
            )
            SELECT
              bc.blotter_case_id  AS case_id,
              bc.blotter_case_num AS case_num,
              COALESCE(bc.blotter_case_name,'') AS case_title,
              COALESCE(ct.complaint_title_name,'') AS case_type,
              COALESCE(cn.case_name,'') AS case_nature,
              s.source_code       AS source,
              s.submission_id,
              p.hearing_date,
              p.hearing_time,
              p.details,
              h.hearing_held,
              h.held_at
            FROM subs s
            JOIN blotter_case bc          ON bc.blotter_case_id = s.blotter_case_id
            LEFT JOIN complaint_title ct  ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn    ON cn.case_nature_id     = bc.case_nature_id
            LEFT JOIN pivot p             ON p.submission_id = s.submission_id
            LEFT JOIN held_per_row h      ON h.submission_id = s.submission_id
            ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
        """, [case_id, case_id, case_id])
        rows = cur.fetchall()

    items = []
    for (cid, case_num, case_title, case_type, case_nature, source,
         submission_id, hearing_date, hearing_time, details, hearing_held, held_at) in rows:
        held_at_fmt = None
        if held_at:
            try:
                held_at_fmt = timezone.localtime(held_at).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                try:
                    held_at_fmt = held_at.strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    held_at_fmt = str(held_at)

        items.append({
            "case_id": cid,
            "case_num": case_num,
            "case_title": case_title,
            "case_type": case_type,
            "case_nature": case_nature,
            "source": source,
            "submission_id": submission_id,
            "hearing_date": hearing_date,
            "hearing_time": hearing_time,
            "details": details,
            "hearing_held": bool(hearing_held),
            "held_at": held_at,
            "held_at_fmt": held_at_fmt,
        })

    return render(request, "lupon_mem/hearing_list.html", {
        "items": items,
        "dev_mode": bool(getattr(settings, "DEBUG", False) or (request.GET.get("dev") == "1")),
    })



# lupon_mem/views.py (add near other imports)
from django.utils import timezone

# helper already present
def _toi(x):
    try:
        return int(x) if x not in (None, "", "0") else None
    except Exception:
        return None
    
@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_hearing_schedule(request: HttpRequest, case_id: int):
    """
    Per-hearing page (Mediation/Conciliation).
    NEW:
      • hearing_index/label (1st/2nd/3rd …)
      • Per-hearing Med-ATT count using [submitted_at, next_submitted_at) window
      • 'Add Mediation Attendance' button re-enables for 2nd/3rd hearings
    """
    sid = _toi(request.GET.get("sid"))

    # 1) All KP-8/KP-12 hearing notices for this case, newest first for default pick
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id,
                   s.form_id,
                   UPPER(kf.form_code)   AS code,
                   s.submitted_at
              FROM blotter_kp_submission s
              JOIN kp_form kf ON kf.form_id = s.form_id
             WHERE s.blotter_case_id=%s
               AND UPPER(kf.form_code) IN ('KP-8','KP-12')
             ORDER BY s.submitted_at ASC, s.submission_id ASC
        """, [case_id])
        all_hearings = cur.fetchall() or []

    if not all_hearings:
        # No hearing yet; render a soft page
        return render(request, "lupon_mem/case_hearing_schedule.html", {
            "case_id": case_id,
            "hearing_source": None,
            "hearing_date": None,
            "hearing_time": None,
            "complainants": [],
            "respondents": [],
            "details": None,
            "picked_submission_id": None,
            "mediation_photos": [],
            "has_attendance": False,
            "med_attendance_count": 0,
            "med_attendance_ord_label": None,
            "hearing_held": False,
            "held_at_fmt": None,
            "dev_mode": bool(getattr(settings, "DEBUG", False) or request.GET.get("dev") == "1"),
            "hearing_index": None,
            "hearing_label": None,
        })

    # Decide which hearing to show:
    #   If sid provided -> that hearing; else show the latest (last in ASC list)
    idx = None
    if sid:
        for i, (sub_id, _, _, _) in enumerate(all_hearings):
            if sub_id == sid:
                idx = i
                break
    if idx is None:
        idx = len(all_hearings) - 1  # latest

    picked_submission_id, form_id, form_code, submitted_at = all_hearings[idx]
    hearing_source = 'KP-8' if form_code == 'KP-8' else 'KP-12'
    next_submitted_at = None
    if idx + 1 < len(all_hearings):
        next_submitted_at = all_hearings[idx + 1][3]  # submitted_at of next hearing

    # 2) Pull the date/time pair from that form (appearance/hearing)
    hearing_date = hearing_time = None
    if form_id and picked_submission_id:
        with connection.cursor() as cur:
            cur.execute("""
                WITH wanted AS (
                  SELECT f.field_id, LOWER(f.field_code) AS code
                    FROM kp_form_field kff
                    JOIN kp_field f ON f.field_id = kff.field_id
                   WHERE kff.form_id=%s
                     AND LOWER(f.field_code) IN ('appearance_date','appearance_time','hearing_date','hearing_time')
                )
                SELECT w.code, a.value_json
                  FROM wanted w
                  JOIN blotter_kp_answer a
                    ON a.submission_id=%s AND a.field_id=w.field_id
            """, [form_id, picked_submission_id])
            pairs = dict(cur.fetchall() or [])

        def _clean(v):
            if v is None: return None
            if isinstance(v, str) and len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                return v[1:-1]
            if isinstance(v, dict):
                for k in ("value", "text", "date", "time"):
                    if k in v and v[k]:
                        return v[k]
            return v

        hearing_date = _clean(pairs.get('hearing_date')) or _clean(pairs.get('appearance_date'))
        hearing_time = _clean(pairs.get('hearing_time')) or _clean(pairs.get('appearance_time'))

    # 3) Parties for header
    with connection.cursor() as cur:
        cur.execute("""SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) 
                         FROM complainant_case cc JOIN person p ON p.person_id=cc.person_id
                        WHERE cc.blotter_case_id=%s ORDER BY 1""", [case_id])
        complainants = [r[0] for r in cur.fetchall()]
        cur.execute("""SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) 
                         FROM respondent_case rc JOIN person p ON p.person_id=rc.person_id
                        WHERE rc.blotter_case_id=%s ORDER BY 1""", [case_id])
        respondents = [r[0] for r in cur.fetchall()]

    # 4) Held status: any HELD after this notice’s submitted_at and before the next hearing (if any)
    held_at = None
    with connection.cursor() as cur:
        cur.execute("""
            SELECT MAX(cpt.date_processed)
              FROM case_progress_tracking cpt
              JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
             WHERE cpt.blotter_case_id=%s
               AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
               AND cpt.date_processed >= %s
               AND (%s IS NULL OR cpt.date_processed < %s)
        """, [case_id, submitted_at, next_submitted_at, next_submitted_at])
        r = cur.fetchone()
        held_at = r[0] if r else None

    hearing_held = bool(held_at)
    held_at_fmt = None
    if held_at:
        try:
            held_at_fmt = timezone.localtime(held_at).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            held_at_fmt = getattr(held_at, "strftime", lambda *_: None)("%b %d, %Y %I:%M %p")

    # 5) Per-hearing Mediation Attendance count using the time window of this hearing only
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.blotter_case_id=%s
               AND UPPER(f.form_code)='MED-ATT-2025'
               AND UPPER(s.status)='SUBMITTED'
               AND s.submitted_at >= %s
               AND (%s IS NULL OR s.submitted_at < %s)
        """, [case_id, submitted_at, next_submitted_at, next_submitted_at])
        med_attendance_count = int(cur.fetchone()[0] or 0)

    # Photos list (still tie to current hearing when saving/uploading)
    mediation_photos = _list_mediation_photos(case_id, picked_submission_id)

    # Old guard (case-level) retained but we’ll primarily use per-hearing count above
    has_attendance = med_attendance_count > 0 or _has_mediation_attendance(case_id)

    # Label helpers
    def _ordinal(n: int) -> str:
        s = {1:"st",2:"nd",3:"rd"}.get(0 if n%100 in (11,12,13) else n%10, "th")
        return f"{n}{s}"

    hearing_index = idx + 1  # 1-based
    hearing_label = f"{_ordinal(hearing_index)} Hearing"
    med_attendance_ord_label = (
        f"{_ordinal(med_attendance_count)} Mediation Attendance successfully attached"
        if med_attendance_count >= 1 else None
    )

    dev_mode = bool(getattr(settings, "DEBUG", False) or request.GET.get("dev") == "1")

    return render(request, "lupon_mem/case_hearing_schedule.html", {
        "case_id": case_id,
        "hearing_source": hearing_source,          # "KP-8" | "KP-12"
        "hearing_date": hearing_date,
        "hearing_time": hearing_time,
        "complainants": complainants,
        "respondents": respondents,
        "details": None,
        "picked_submission_id": picked_submission_id,

        # Per-hearing scope
        "hearing_index": hearing_index,
        "hearing_label": hearing_label,
        "med_attendance_count": med_attendance_count,
        "med_attendance_ord_label": med_attendance_ord_label,

        # Media & flags
        "mediation_photos": mediation_photos,
        "has_attendance": has_attendance,
        "hearing_held": hearing_held,
        "held_at_fmt": held_at_fmt,
        "dev_mode": dev_mode,
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_summon_list(request: HttpRequest, case_id: int):
    """Per-case KP-9 summons list (served date/time + officer’s return)."""
    with connection.cursor() as cur:
        cur.execute("""
            WITH f AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1
            ),
            subs AS (
              SELECT s.submission_id
              FROM blotter_kp_submission s
              WHERE s.blotter_case_id=%s AND s.form_id=(SELECT form_id FROM f)
              ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                       s.submitted_at DESC NULLS LAST,
                       s.submission_id DESC
            ),
            ans AS (
              SELECT s.submission_id, LOWER(kf.field_code) AS code,
                     TRIM(BOTH '"' FROM a.value_json::text) AS v
              FROM subs s
              JOIN blotter_kp_answer a ON a.submission_id=s.submission_id
              JOIN kp_field kf ON kf.field_id=a.field_id
              WHERE LOWER(kf.field_code) IN (
                'summon_month','summon_date','summon_year','summon_time',
                'served_to','addr_to','offcret_serve_month','offcret_serve_date','offcret_serve_year',
                'month_offcret','date_offcret','ofcret_year'
              )
            )
            SELECT
              s.submission_id,
              COALESCE(
                NULLIF(TRIM(
                  (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_month') || ' ' ||
                  (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_date')  || ', ' ||
                  (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_year')
                ), ''), '—'
              ) AS served_date,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_time'),'') AS served_time,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='served_to'),
                       (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='addr_to'), 'Someone') AS who,
              COALESCE(
                NULLIF(TRIM(
                  COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_month'),
                           (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='month_offcret')) || ' ' ||
                  COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_date'),
                           (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='date_offcret'))  || ', ' ||
                  COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_year'),
                           (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='ofcret_year'))
                ), ''), '—'
              ) AS officer_return
            FROM subs s
        """, [case_id])
        rows = cur.fetchall()

    # Shape it like hearing rows so we can reuse hearing_list.html
    items = []
    for sid, served_date, served_time, who, officer_ret in rows:
        details = f"Served to: {who}"
        if officer_ret and officer_ret != "—":
            details += f" • Officer's Return: {officer_ret}"
        items.append({
            "case_id": case_id,
            "case_num": "", "case_title": f"Summons #{sid}",
            "case_type": "KP-9", "case_nature": "",
            "hearing_date": served_date or "",
            "hearing_time": served_time or "",
            "details": details
        })

    return render(request, "lupon_mem/hearing_list.html", {
        "items": items,
        "q": "",
        "page_title": "Summons (KP-9) for this Case"
    })


# views.py
from django.utils import timezone
from django.http import HttpResponseNotFound

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def hearing_list(request: HttpRequest):
    """
    All-cases list of KP-8/KP-12 notices with per-notice Held status.
    """
    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (
              SELECT form_id, UPPER(form_code) AS code
              FROM kp_form
              WHERE UPPER(form_code) IN ('KP-8','KP-12')
            ),
            subs AS (
              SELECT
                s.submission_id,
                s.form_id,
                (SELECT code FROM forms f WHERE f.form_id = s.form_id) AS source_code,
                s.blotter_case_id,
                s.submitted_at
              FROM blotter_kp_submission s
              JOIN forms f ON f.form_id = s.form_id
            ),
            ans AS (
              SELECT
                s.submission_id,
                LOWER(kf.field_code) AS code,
                TRIM(BOTH '"' FROM a.value_json::text) AS v
              FROM subs s
              JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
              JOIN kp_field kf         ON kf.field_id      = a.field_id
              WHERE LOWER(kf.field_code) IN (
                'appearance_date','appearance_time',
                'hearing_date','hearing_time',
                'details','text box 1','venue'
              )
            ),
            pivot AS (
              SELECT
                s.submission_id,
                MAX(CASE WHEN code IN ('hearing_date','appearance_date') THEN NULLIF(v,'') END) AS hearing_date,
                MAX(CASE WHEN code IN ('hearing_time','appearance_time') THEN NULLIF(v,'') END) AS hearing_time,
                MAX(CASE WHEN code IN ('details','text box 1','venue')   THEN NULLIF(v,'') END) AS details
              FROM subs s
              LEFT JOIN ans ON ans.submission_id = s.submission_id
              GROUP BY s.submission_id
            ),
            held_per_row AS (
              SELECT
                s.submission_id,
                EXISTS(
                  SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                  WHERE cpt.blotter_case_id = s.blotter_case_id
                    AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                    AND cpt.date_processed > s.submitted_at
                ) AS hearing_held,
                (
                  SELECT MAX(cpt.date_processed)
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                  WHERE cpt.blotter_case_id = s.blotter_case_id
                    AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                    AND cpt.date_processed > s.submitted_at
                ) AS held_at
              FROM subs s
            )
            SELECT
              bc.blotter_case_id  AS case_id,
              bc.blotter_case_num AS case_num,
              COALESCE(bc.blotter_case_name,'') AS case_title,
              COALESCE(ct.complaint_title_name,'') AS case_type,
              COALESCE(cn.case_name,'') AS case_nature,
              s.source_code       AS source,
              s.submission_id,
              p.hearing_date,
              p.hearing_time,
              p.details,
              h.hearing_held,
              h.held_at
            FROM subs s
            JOIN blotter_case bc          ON bc.blotter_case_id = s.blotter_case_id
            LEFT JOIN complaint_title ct  ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn    ON cn.case_nature_id     = bc.case_nature_id
            LEFT JOIN pivot p             ON p.submission_id = s.submission_id
            LEFT JOIN held_per_row h      ON h.submission_id = s.submission_id
            ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 500
        """)
        rows = cur.fetchall()

    # shape to dicts + format held_at
    items = []
    for (case_id, case_num, case_title, case_type, case_nature, source,
         submission_id, hearing_date, hearing_time, details, hearing_held, held_at) in rows:
        held_at_fmt = None
        if held_at:
            try:
                held_at_fmt = timezone.localtime(held_at).strftime("%b %d, %Y %I:%M %p")
            except Exception:
                try:
                    held_at_fmt = held_at.strftime("%b %d, %Y %I:%M %p")
                except Exception:
                    held_at_fmt = str(held_at)

        items.append({
            "case_id": case_id,
            "case_num": case_num,
            "case_title": case_title,
            "case_type": case_type,
            "case_nature": case_nature,
            "source": source,
            "submission_id": submission_id,
            "hearing_date": hearing_date,
            "hearing_time": hearing_time,
            "details": details,
            "hearing_held": bool(hearing_held),
            "held_at": held_at,
            "held_at_fmt": held_at_fmt,
        })

    return render(request, "lupon_mem/hearing_list.html", {
        "items": items,
        "dev_mode": bool(getattr(settings, "DEBUG", False) or (request.GET.get("dev") == "1")),
    })


# lupon_mem/views.py
from django.utils import timezone
from django.views.decorators.http import require_POST

# imports (only include what you need if these already exist in your file)
from django.db import connection, transaction
from django.utils import timezone
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.http import HttpRequest

# -------------------------------------------------------------------
# Helper: persist attendance flags for a specific hearing (KP-8/KP-12)
# - Works even if the table has no unique constraint (no ON CONFLICT).
# - We UPDATE first; if no row matched, we INSERT.
# - Booleans are written as native Postgres boolean (true/false).
# -------------------------------------------------------------------



def _maybe_upsert_hearing_attendance(
    case_id: int,
    source_code: str,        # 'KP-8' or 'KP-12'
    notice_sid: int,         # submission_id of the notice
    compl_attended: bool,
    resp_attended: bool,
    settlement: str | None,
    remarks: str | None,
) -> None:
    with connection.cursor() as cur:
        # ensure cache table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hearing_attendance (
              blotter_case_id      int      NOT NULL,
              source_code          text     NOT NULL,  -- 'KP-8' / 'KP-12'
              notice_submission_id int      NOT NULL,
              held_at              timestamptz DEFAULT NOW(),
              complainant_attended boolean,
              respondent_attended  boolean,
              settlement_outcome   text,
              remarks              text
            );
        """)

        # try UPDATE first
        cur.execute("""
            UPDATE hearing_attendance
               SET held_at = NOW(),
                   complainant_attended = %s,
                   respondent_attended  = %s,
                   settlement_outcome   = NULLIF(%s,''),
                   remarks              = NULLIF(%s,'')
             WHERE blotter_case_id = %s
               AND source_code = %s
               AND notice_submission_id = %s
        """, [
            compl_attended, resp_attended,
            (settlement or ""), (remarks or ""),
            case_id, source_code, notice_sid
        ])

        # if no existing row, INSERT
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO hearing_attendance
                  (blotter_case_id, source_code, notice_submission_id,
                   held_at, complainant_attended, respondent_attended,
                   settlement_outcome, remarks)
                VALUES (%s,%s,%s, NOW(), %s,%s, NULLIF(%s,''), NULLIF(%s,''))
            """, [
                case_id, source_code, notice_sid,
                compl_attended, resp_attended,
                (settlement or ""), (remarks or "")
            ])



# =========================== VIEWS ===========================

@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
@require_POST
def mediation_complete(request, case_id: int):
    settlement = (request.POST.get('settlement') or '').upper().strip()
    remarks    = (request.POST.get('remarks') or '').strip()

    # ✅ 1) Must have Mediation Attendance before marking held
    if not _has_med_attendance(case_id):
        messages.error(request, "Please add Mediation Attendance first before marking the mediation as held.")
        return redirect('lupon_mem:case_hearing_schedule', case_id)

    # ✅ 2) If SETTLED → force KP-16 first
    if settlement == 'SETTLED':
        messages.info(request, "Please complete the Amicable Settlement (KP-16) before finalizing as SETTLED.")
        return redirect('lupon_mem:open_kp16_from_hearing', case_id=case_id)

    # ---- parse POST
    raw_sid = request.POST.get("submission_id")
    submission_id = int(raw_sid) if raw_sid and raw_sid.isdigit() else None
    compl_attended = bool(request.POST.get("compl_attended"))
    resp_attended  = bool(request.POST.get("resp_attended"))
    settlement     = (request.POST.get("settlement") or "").strip().upper() or "PENDING"
    kp16_confirmed = (request.POST.get("kp16_confirmed") == "1")
    remarks        = (request.POST.get("remarks") or "").strip() or None
    staff_id       = (request.session.get("auth") or {}).get("staff_id")
    now_iso        = timezone.now().isoformat(timespec="seconds")

    print(f"\n[HEARING-HELD][KP-8][POST] case_id={case_id}")
    print("[HEARING-HELD][KP-8] payload:", {
        "submission_id": submission_id, "compl_attended": compl_attended,
        "resp_attended": resp_attended, "settlement": settlement,
        "kp16_confirmed": kp16_confirmed, "remarks": remarks,
        "staff_id": staff_id, "timestamp": now_iso,
    })

    # ---- pick the submission_id if missing, validate it is KP-8 for this case
    with connection.cursor() as cur:
        if not submission_id:
            cur.execute("""
                SELECT s.submission_id
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id=s.form_id
                WHERE s.blotter_case_id=%s AND UPPER(f.form_code)='KP-8'
                ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                         s.submitted_at DESC NULLS LAST,
                         s.submission_id DESC
                LIMIT 1
            """, [case_id])
            r = cur.fetchone()
            submission_id = int(r[0]) if r else None

        cur.execute("""
            SELECT COUNT(*) FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id=s.form_id
            WHERE s.submission_id=%s AND s.blotter_case_id=%s AND UPPER(f.form_code)='KP-8'
        """, [submission_id, case_id])
        valid = (cur.fetchone() or [0])[0] == 1

    if not submission_id or not valid:
        messages.error(request, "Invalid KP-8 submission selected.")
        return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)

    # ---- compute the rank (1st/2nd/3rd) of this schedule among all KP-8/KP-12 for the case
    with connection.cursor() as cur:
        cur.execute("""
            WITH sched AS (
              SELECT s.submission_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.blotter_case_id
                       ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
                     ) AS rn
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id=s.form_id
              WHERE s.blotter_case_id=%s AND UPPER(f.form_code) IN ('KP-8','KP-12')
            )
            SELECT rn FROM sched WHERE submission_id=%s
        """, [case_id, submission_id])
        row = cur.fetchone()
        sched_rn = int(row[0]) if row else None

        # how many HELD/CONCILIATION HELD already
        cur.execute("""
            SELECT COUNT(*)::int FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
            WHERE cpt.blotter_case_id=%s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
        """, [case_id])
        held_so_far = int((cur.fetchone() or [0])[0])

    print(f"[HEARING-HELD][KP-8] schedule_rn={sched_rn}  held_so_far={held_so_far}  expected_next={(held_so_far+1)}")

    # ---- resolve progress_type_id for 'HEARING HELD'
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_progress_type_id
            FROM case_progress_type
            WHERE UPPER(case_progress_type_name)='HEARING HELD'
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            messages.error(request, "Progress type 'HEARING HELD' not configured.")
            return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)
        progress_type_id = int(row[0])

    print("[HEARING-HELD][KP-8] using case_progress_type_id=", progress_type_id)

    # ---- insert tracking row
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, date_processed, remarks, processed_by_id)
                VALUES (%s,%s, now(),
                        %s,
                        %s)
                RETURNING progress_tracking_id, date_processed
            """, [
                case_id,
                progress_type_id,
                remarks or f"KP-8 held (sched #{sched_rn}); comp_att={compl_attended}, resp_att={resp_attended}",
                staff_id,
            ])
            trk_id, dtp = cur.fetchone()
    print(f"[HEARING-HELD][KP-8] inserted tracking_id={trk_id}  date_processed={dtp}")

    # ---- persist attendance flags (no models; safe upsert)
    _maybe_upsert_hearing_attendance(
        case_id=case_id,
        source_code="KP-8",
        notice_sid=submission_id,
        compl_attended=compl_attended,
        resp_attended=resp_attended,
        settlement=settlement,
        remarks=remarks,
    )

    # ---- if SETTLED and KP-16 already done, flip case to SETTLED (defensive)
    if settlement == "SETTLED" and kp16_confirmed:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Marked settled from KP-8 (KP-16 done)', staff_id])
            print("[HEARING-HELD][KP-8] settlement status set to SETTLED via fn_set_case_settlement().")
            messages.success(request, "Marked HELD and settlement set to SETTLED.")
        except Exception as e:
            print("[HEARING-HELD][KP-8][WARN] Failed to set settlement:", e)
            messages.success(request, "Marked HELD. (Could not update settlement automatically.)")
    else:
        messages.success(request, "Mediation marked HELD.")

    # bounce back to the same schedule
    return redirect(f"{reverse('lupon_mem:case_hearing_schedule', args=[case_id])}?sid={submission_id}")


@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def conciliation_complete(request: HttpRequest, case_id: int):
    """
    Mark a KP-12 hearing as HELD (CONCILIATION HELD).
    Same debug prints as mediation_complete.
    """
    raw_sid = request.POST.get("submission_id")
    submission_id = int(raw_sid) if raw_sid and raw_sid.isdigit() else None
    compl_attended = bool(request.POST.get("compl_attended"))
    resp_attended  = bool(request.POST.get("resp_attended"))
    settlement     = (request.POST.get("settlement") or "").strip().upper() or "PENDING"
    kp16_confirmed = (request.POST.get("kp16_confirmed") == "1")
    remarks        = (request.POST.get("remarks") or "").strip() or None
    staff_id       = (request.session.get("auth") or {}).get("staff_id")
    now_iso        = timezone.now().isoformat(timespec="seconds")

    print(f"\n[HEARING-HELD][KP-12][POST] case_id={case_id}")
    print("[HEARING-HELD][KP-12] payload:", {
        "submission_id": submission_id, "compl_attended": compl_attended,
        "resp_attended": resp_attended, "settlement": settlement,
        "kp16_confirmed": kp16_confirmed, "remarks": remarks,
        "staff_id": staff_id, "timestamp": now_iso,
    })

    with connection.cursor() as cur:
        if not submission_id:
            cur.execute("""
                SELECT s.submission_id
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id=s.form_id
                WHERE s.blotter_case_id=%s AND UPPER(f.form_code)='KP-12'
                ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                         s.submitted_at DESC NULLS LAST,
                         s.submission_id DESC
                LIMIT 1
            """, [case_id])
            r = cur.fetchone()
            submission_id = int(r[0]) if r else None

        cur.execute("""
            SELECT COUNT(*) FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id=s.form_id
            WHERE s.submission_id=%s AND s.blotter_case_id=%s AND UPPER(f.form_code)='KP-12'
        """, [submission_id, case_id])
        valid = (cur.fetchone() or [0])[0] == 1

    if not submission_id or not valid:
        messages.error(request, "Invalid KP-12 submission selected.")
        return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)

    with connection.cursor() as cur:
        cur.execute("""
            WITH sched AS (
              SELECT s.submission_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.blotter_case_id
                       ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
                     ) AS rn
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id=s.form_id
              WHERE s.blotter_case_id=%s AND UPPER(f.form_code) IN ('KP-8','KP-12')
            )
            SELECT rn FROM sched WHERE submission_id=%s
        """, [case_id, submission_id])
        row = cur.fetchone()
        sched_rn = int(row[0]) if row else None

        cur.execute("""
            SELECT COUNT(*)::int FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id=cpt.case_progress_type_id
            WHERE cpt.blotter_case_id=%s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
        """, [case_id])
        held_so_far = int((cur.fetchone() or [0])[0])

    print(f"[HEARING-HELD][KP-12] schedule_rn={sched_rn}  held_so_far={held_so_far}  expected_next={(held_so_far+1)}")

    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_progress_type_id
            FROM case_progress_type
            WHERE UPPER(case_progress_type_name)='CONCILIATION HELD'
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            messages.error(request, "Progress type 'CONCILIATION HELD' not configured.")
            return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)
        progress_type_id = int(row[0])

    print("[HEARING-HELD][KP-12] using case_progress_type_id=", progress_type_id)

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, date_processed, remarks, processed_by_id)
                VALUES (%s,%s, now(),
                        %s,
                        %s)
                RETURNING progress_tracking_id, date_processed
            """, [
                case_id,
                progress_type_id,
                remarks or f"KP-12 held (sched #{sched_rn}); comp_att={compl_attended}, resp_att={resp_attended}",
                staff_id,
            ])
            trk_id, dtp = cur.fetchone()
    print(f"[HEARING-HELD][KP-12] inserted tracking_id={trk_id}  date_processed={dtp}")

    # ---- persist attendance flags (no models; safe upsert)
    _maybe_upsert_hearing_attendance(
        case_id=case_id,
        source_code="KP-12",
        notice_sid=submission_id,
        compl_attended=compl_attended,
        resp_attended=resp_attended,
        settlement=settlement,
        remarks=remarks,
    )

    if settlement == "SETTLED" and kp16_confirmed:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Marked settled from KP-12 (KP-16 done)', staff_id])
            print("[HEARING-HELD][KP-12] settlement status set to SETTLED via fn_set_case_settlement().")
            messages.success(request, "Marked HELD and settlement set to SETTLED.")
        except Exception as e:
            print("[HEARING-HELD][KP-12][WARN] Failed to set settlement:", e)
            messages.success(request, "Marked HELD. (Could not update settlement automatically.)")
    else:
        messages.success(request, "Conciliation marked HELD.")

    return redirect(f"{reverse('lupon_mem:case_hearing_schedule', args=[case_id])}?sid={submission_id}")


@session_login_required
@role_required(*LUPON_ROLES)
def open_kp16_from_hearing(request: HttpRequest, case_id: int):
    """
    Opens the KP-16 form builder and remembers which hearing (notice SID)
    triggered it so we can auto-mark HELD after KP-16 submission.
    """
    sid = request.GET.get("sid")  # KP-8/KP-12 submission_id used as the hearing notice id
    try:
        sid_int = int(sid) if sid and sid.isdigit() else None
    except Exception:
        sid_int = None

    if sid_int:
        request.session["auto_mark_hearing_after_kp16_sid"] = sid_int
        request.session["auto_mark_hearing_case_id"] = case_id
        request.session.modified = True
        print(f"[open_kp16_from_hearing] remembered sid={sid_int} for case_id={case_id}")

    # Redirect straight to the KP-16 builder by code
    return redirect("lupon_mem:form_builder_by_code", case_id=case_id, form_code="KP-16")

        

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def hearing_complete(request: HttpRequest, case_id: int):
    settlement = (request.POST.get("settlement_status") or "").strip()
    remarks    = (request.POST.get("remarks") or "").strip() or None
    staff_id   = (request.session.get("auth") or {}).get("staff_id")
    kind       = (request.POST.get("kind") or "").strip().upper()  # 'MEDIATION' | 'CONCILIATION'

    compl_attended = request.POST.get("compl_attended") == "on"
    resp_attended  = request.POST.get("resp_attended") == "on"

    if not settlement:
        return HttpResponseBadRequest("Settlement status is required.")

    # decide progress label based on source
    progress_name = "HEARING HELD"
    if kind == "CONCILIATION":
        progress_name = "CONCILIATION HELD"

    try:
        with connection.cursor() as cur:
            # 1) mark held (MEDIATION or CONCILIATION)
            cur.execute("SELECT * FROM fn_add_case_progress(%s,%s,%s,%s)",
                        [case_id, progress_name, remarks, staff_id])

            # 2) attendance notes
            if not compl_attended:
                cur.execute("SELECT * FROM fn_add_case_progress(%s,%s,%s,%s)",
                            [case_id, 'HEARING NO-SHOW (COMPLAINANT)', remarks, staff_id])
            if not resp_attended:
                cur.execute("SELECT * FROM fn_add_case_progress(%s,%s,%s,%s)",
                            [case_id, 'HEARING NO-SHOW (RESPONDENT)', remarks, staff_id])

        # 3) settlement handling
        if settlement.upper().startswith('SETTLED'):
            # Do NOT set case to SETTLED here. Force KP-16 first.
            messages.info(request, "Please complete KP-16 to finalize the settlement.")
            return redirect(reverse("lupon_mem:open_kp16_from_hearing", args=[case_id]))
        else:
            # keep it pending/not settled via your function
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, settlement, remarks, staff_id])

    except Exception as e:
        messages.error(request, f"Failed to complete hearing: {e}")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    messages.success(request, f"{progress_name} recorded. Settlement set to “{settlement}”.")
    return redirect("lupon_mem:case_detail", case_id=case_id)



# views.py
# lupon_mem/views.py  (replace your summon_attendance with this version)

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def summon_attendance(request: HttpRequest, case_id: int):
    """
    Lists all KP-9 submissions for a case with served date/time + 'served to',
    and lets the user mark ATTENDED / NO SHOW per summons.
    """
    # Case header (for the page)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_num,
                   COALESCE(bc.blotter_case_name,'') AS case_title,
                   COALESCE(ct.complaint_title_name,'') AS complaint_title,
                   COALESCE(cn.case_name,'')           AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn ON cn.case_nature_id       = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        header = cur.fetchone()
        if not header:
            return HttpResponseNotFound("Case not found.")
        case_num, case_title, complaint_title, case_nature = header

        # Pull KP-9 submissions + served data + current attendance status (if any)
        cur.execute("""
            WITH f AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1
            ),
            subs AS (
              SELECT s.submission_id, s.submitted_at
              FROM blotter_kp_submission s
              WHERE s.blotter_case_id=%s AND s.form_id=(SELECT form_id FROM f)
              ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                       s.submitted_at DESC NULLS LAST,
                       s.submission_id DESC
            ),
            ans AS (
              SELECT s.submission_id, LOWER(kf.field_code) AS code,
                     TRIM(BOTH '"' FROM a.value_json::text) AS v
              FROM subs s
              JOIN blotter_kp_answer a ON a.submission_id=s.submission_id
              JOIN kp_field kf ON kf.field_id=a.field_id
              WHERE LOWER(kf.field_code) IN (
                'summon_month','summon_date','summon_year','summon_time',
                'served_to','addr_to',
                'offcret_serve_month','offcret_serve_date','offcret_serve_year',
                'month_offcret','date_offcret','ofcret_year'
              )
            )
            SELECT
              s.submission_id,
              s.submitted_at,
              COALESCE(NULLIF(TRIM(
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_month'),'') || ' ' ||
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_date'),'')  || ', ' ||
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_year'),'')
              ),''),'—')                   AS served_date,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_time'),'') AS served_time,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='served_to'),
                       (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='addr_to'),
                       '—')                 AS served_to,
              COALESCE(NULLIF(TRIM(
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_month'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='month_offcret')) || ' ' ||
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_date'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='date_offcret'))  || ', ' ||
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_year'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='ofcret_year'))
              ),''),'—')                   AS officer_return,
              a.status,
              a.remarks,
              to_char(a.marked_at, 'YYYY-MM-DD HH24:MI') AS marked_at,
              a.no_show_party
            FROM subs s
            LEFT JOIN kp9_attendance a ON a.submission_id = s.submission_id
        """, [case_id])
        rows = cur.fetchall()

    items = []
    for (sid, submitted_at, served_date, served_time, served_to, officer_ret,
         status, remarks, marked_at, no_show_party) in rows:
        items.append({
            "submission_id": sid,
            "served_date": served_date or "—",
            "served_time": served_time or "—",
            "served_to":   served_to   or "—",
            "officer_return": officer_ret or "—",
            "status": (status or "").upper() if status else None,
            "remarks": remarks or "",
            "marked_at": marked_at or "",
            "no_show_party": (no_show_party or "").upper() if no_show_party else None,
        })

    return render(request, "lupon_mem/summon_attendance.html", {
        "case_id": case_id,
        "case_num": case_num,
        "case_title": case_title,
        "complaint_title": complaint_title,
        "case_nature": case_nature,
        "items": items,
    })



from django.views.decorators.http import require_POST
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def summon_attendance(request: HttpRequest, case_id: int):
    """
    Lists all KP-9 submissions for a case with served date/time + 'served to',
    and lets the user mark ATTENDED / NO SHOW per summons (including who didn't show).
    """
    # ---- Case header (for the page) ----
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_num,
                   COALESCE(bc.blotter_case_name,'')     AS case_title,
                   COALESCE(ct.complaint_title_name,'')  AS complaint_title,
                   COALESCE(cn.case_name,'')             AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn ON cn.case_nature_id       = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        header = cur.fetchone()
        if not header:
            return HttpResponseNotFound("Case not found.")
        case_num, case_title, complaint_title, case_nature = header

        # ---- KP-9 submissions + served data + attendance status ----
        cur.execute("""
            WITH f AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1
            ),
            subs AS (
              SELECT s.submission_id, s.submitted_at
              FROM blotter_kp_submission s
              WHERE s.blotter_case_id=%s AND s.form_id=(SELECT form_id FROM f)
              ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                       s.submitted_at DESC NULLS LAST,
                       s.submission_id DESC
            ),
            ans AS (
              SELECT s.submission_id, LOWER(kf.field_code) AS code,
                     TRIM(BOTH '"' FROM a.value_json::text) AS v
              FROM subs s
              JOIN blotter_kp_answer a ON a.submission_id=s.submission_id
              JOIN kp_field kf ON kf.field_id=a.field_id
              WHERE LOWER(kf.field_code) IN (
                'summon_month','summon_date','summon_year','summon_time',
                'served_to','addr_to',
                'offcret_serve_month','offcret_serve_date','offcret_serve_year',
                'month_offcret','date_offcret','ofcret_year'
              )
            )
            SELECT
              s.submission_id,
              s.submitted_at,
              COALESCE(NULLIF(TRIM(
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_month'),'') || ' ' ||
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_date'),'')  || ', ' ||
                 COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_year'),'')
              ),''),'—')                   AS served_date,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='summon_time'),'') AS served_time,
              COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='served_to'),
                       (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='addr_to'),
                       '—')                 AS served_to,
              COALESCE(NULLIF(TRIM(
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_month'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='month_offcret')) || ' ' ||
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_date'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='date_offcret'))  || ', ' ||
                COALESCE((SELECT v FROM ans WHERE submission_id=s.submission_id AND code='offcret_serve_year'),
                         (SELECT v FROM ans WHERE submission_id=s.submission_id AND code='ofcret_year'))
              ),''),'—')                   AS officer_return,
              a.status,
              a.remarks,
              to_char(a.marked_at, 'YYYY-MM-DD HH24:MI') AS marked_at,
              a.no_show_party
            FROM subs s
            LEFT JOIN kp9_attendance a ON a.submission_id = s.submission_id
        """, [case_id])
        rows = cur.fetchall()

    # ---- Shape rows for template ----
    items = []
    for (sid, submitted_at, served_date, served_time, served_to, officer_ret,
         status, remarks, marked_at, no_show_party) in rows:  # NOTE: 10 values now
        items.append({
            "submission_id": sid,
            "served_date": served_date or "—",
            "served_time": served_time or "—",
            "served_to":   served_to   or "—",
            "officer_return": officer_ret or "—",
            "status": (status or "").upper() if status else None,
            "remarks": remarks or "",
            "marked_at": marked_at or "",
            "no_show_party": (no_show_party or "").upper() if no_show_party else None,
        })

    # nice caption like "BELLOSILLO vs. SANAOL"
    case_caption = case_title

    return render(request, "lupon_mem/summon_attendance.html", {
        "case_id": case_id,
        "case_num": case_num,
        "case_title": case_title,
        "case_caption": case_caption,
        "complaint_title": complaint_title,
        "case_nature": case_nature,
        "items": items,
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def summon_set_status(request: HttpRequest, submission_id: int):
    status = (request.POST.get("status") or "").strip().upper()
    if status not in {"ATTENDED", "NO SHOW"}:
        return HttpResponseBadRequest("Invalid status.")

    remarks = (request.POST.get("remarks") or "").strip() or None
    party   = (request.POST.get("no_show_party") or "").strip().upper() or None
    staff_id = (request.session.get("auth") or {}).get("staff_id")

    # If NO SHOW, require party; if ATTENDED, force None
    if status == "NO SHOW":
        if party not in {"COMPLAINANT","RESPONDENT","BOTH"}:
            return HttpResponseBadRequest("Please specify who did not show.")
    else:
        party = None

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id=s.form_id
                WHERE s.submission_id=%s AND UPPER(f.form_code)='KP-9'
            """, [submission_id])
            if not cur.fetchone():
                return HttpResponseBadRequest("Not a KP-9 submission.")

            cur.execute("""
                INSERT INTO kp9_attendance (submission_id, status, remarks, marked_by, marked_at, no_show_party)
                VALUES (%s, %s, %s, %s, now(), %s)
                ON CONFLICT (submission_id)
                DO UPDATE SET status=EXCLUDED.status,
                              remarks=EXCLUDED.remarks,
                              marked_by=EXCLUDED.marked_by,
                              marked_at=EXCLUDED.marked_at,
                              no_show_party=EXCLUDED.no_show_party
            """, [submission_id, status, remarks, staff_id, party])

            cur.execute("SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s", [submission_id])
            row = cur.fetchone()
            case_id = int(row[0]) if row else None

    messages.success(request, f"Summons marked as {status}{' — ' + party if party else ''}.")
    return redirect("lupon_mem:summon_attendance", case_id=case_id) if case_id else redirect("lupon_mem:hearing_list")



@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def mark_hearing_held_dev(request, case_id: int):
    """
    DEV-ONLY: Manually record a HEARING HELD / CONCILIATION HELD at a chosen datetime.
    Prefills from the schedule row; lets you override date/time so the list shows Held immediately.
    """
    # gate: only when DEBUG or ?dev=1 was used anywhere
    dev_allowed = getattr(settings, "DEBUG", False) or (request.META.get("HTTP_REFERER","").find("dev=1") >= 0)
    if not dev_allowed:
        messages.error(request, "Dev mark-held is disabled in production.")
        return redirect("lupon_mem:case_hearing_list", case_id=case_id)

    typ = (request.POST.get("progress_type") or "HEARING HELD").strip().upper()
    if typ not in ("HEARING HELD", "CONCILIATION HELD"):
        typ = "HEARING HELD"

    when_date = (request.POST.get("when_date") or "").strip()
    when_time = (request.POST.get("when_time") or "").strip()
    remarks   = (request.POST.get("remarks") or "").strip() or None
    staff_id  = (request.session.get("auth") or {}).get("staff_id")

    # combine to a timezone-aware datetime; fallback = now
    dt_text = f"{when_date} {when_time}".strip()
    held_at = None
    try:
        # accepts "YYYY-MM-DD HH:MM"
        held_at = timezone.make_aware(datetime.strptime(dt_text, "%Y-%m-%d %H:%M"))
    except Exception:
        try:
            # accepts "YYYY-MM-DD"
            held_at = timezone.make_aware(datetime.strptime(when_date, "%Y-%m-%d"))
        except Exception:
            held_at = timezone.now()

    try:
        with connection.cursor() as cur:
            # lookup case_progress_type_id
            cur.execute("""
                SELECT case_progress_type_id
                FROM case_progress_type
                WHERE UPPER(case_progress_type_name)=%s
                LIMIT 1
            """, [typ])
            row = cur.fetchone()
            if not row:
                messages.error(request, f"Progress type not found: {typ}")
                return redirect("lupon_mem:case_hearing_list", case_id=case_id)
            t_id = int(row[0])

            # insert held row with chosen time
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, remarks, date_processed, processed_by)
                VALUES (%s,%s,%s,%s,%s)
            """, [case_id, t_id, remarks, held_at, staff_id])

        messages.success(request, f"{typ.title()} recorded at {held_at:%Y-%m-%d %H:%M}.")
    except Exception as e:
        messages.error(request, f"Failed to record held: {e}")

    return redirect("lupon_mem:case_hearing_list", case_id=case_id)


    from django.views.decorators.http import require_POST
from django.core.files.uploadedfile import UploadedFile

@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def mediation_photos_upload(request: HttpRequest, case_id: int, submission_id: int):
    """Upload one or more mediation photos (tied to the KP-8 notice submission)."""
    files = request.FILES.getlist("photos[]") or request.FILES.getlist("photos")
    if not files:
        messages.error(request, "Select one or more images to upload.")
        return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)

    bucket = getattr(settings, "SUPABASE_BUCKET", "documents")
    saved = 0
    for f in files:
        if not isinstance(f, UploadedFile):
            continue
        safe = f.name.replace("..", "").replace("/", "_")
        path = f"blotter/{case_id}/mediation/{submission_id}/photos/{safe}"
        try:
            supabase.storage.from_(bucket).upload(path, f.read(),
                {"contentType": f.content_type or "image/jpeg", "upsert": "true"})
            # try to make it viewable
            storage_url = None
            try:
                pub = supabase.storage.from_(bucket).get_public_url(path)
                storage_url = pub.get("publicUrl") if isinstance(pub, dict) else (pub if isinstance(pub, str) else None)
            except Exception:
                pass
            if not storage_url:
                try:
                    signed = supabase.storage.from_(bucket).create_signed_url(path, 60*60*24*7)
                    storage_url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
                except Exception:
                    pass

            # optional: store a row for listing (fits your patterns)
            with connection.cursor() as cur:
                cur.execute("""
                  INSERT INTO case_attachment
                      (blotter_case_id, submission_id, attachment_type, filename, storage_url, path_in_bucket, uploaded_by)
                  VALUES (%s,%s,'MEDIATION_PHOTO',%s,%s,%s,%s)
                """, [case_id, submission_id, safe, storage_url, path,
                      (request.session.get("auth") or {}).get("staff_id")])
            saved += 1
        except Exception:
            continue

    messages.success(request, f"Uploaded {saved} photo(s)." if saved else "No photos were uploaded.")
    return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)


from django.shortcuts import redirect
from django.urls import reverse

def open_med_attendance_from_hearing(request, case_id: int):
    """
    Redirect from the hearing page to the Add Form chooser,
    preselecting the Mediation Attendance form and preserving ?sid.
    """
    sid = request.GET.get("sid")
    target = reverse("lupon_mem:add_form_choose_static", args=[case_id])

    qs = ["code=MED-ATT-2025", "from=hearing"]
    if sid:
        qs.append(f"sid={sid}")

    return redirect(f"{target}?{'&'.join(qs)}")

from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import redirect
from django.core.files.base import ContentFile
from django.conf import settings
from django.db import connection
import io, os, uuid

# Only if you’re using Supabase Option B
from supabase import create_client
# --------------------------------------------
# Upload documentation photos to Supabase
# --------------------------------------------
import os, uuid
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib import messages
from django.db import connection
from django.conf import settings

# using supabase-py v2
from supabase import create_client


def _supabase_client():
    url = getattr(settings, "SUPABASE_URL", "") or ""
    key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "") or ""
    if not (isinstance(url, str) and url and isinstance(key, str) and key):
        raise RuntimeError("Supabase URL/Key are missing or invalid. Check settings/env.")
    return create_client(url, key)



@require_POST
def hearing_media_upload(request, case_id: int):
    """
    Uploads hearing documentation photos to Supabase Storage and stores the
    public URL in case_hearing_media.file_path.
    """
    files = request.FILES.getlist('photos[]')
    submission_id = request.POST.get('submission_id')
    try:
        submission_id = int(submission_id) if submission_id else None
    except ValueError:
        submission_id = None

    if not files:
        messages.warning(request, "No files selected.")
        return redirect('lupon_mem:case_hearing_schedule', case_id)

    sb = _supabase_client()
    bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "case-media")

    saved = 0
    for f in files:
        ext = (os.path.splitext(f.name)[1] or ".bin").lower()
        fname = f"{uuid.uuid4().hex}{ext}"
        # key inside the bucket (no leading slash)
        key = f"case_media/{case_id}/{fname}"

        # Upload bytes to Supabase
        sb.storage.from_(bucket).upload(
            path=key,
            file=f.read(),
            file_options={
                "content_type": f.content_type or "application/octet-stream",
                "cache_control": "3600",
                "upsert": False,
            },
        )

        # Resolve a public URL
        public_url = sb.storage.from_(bucket).get_public_url(key)

        # Persist in DB — store the public URL directly
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO case_hearing_media (
                  blotter_case_id, submission_id, file_path, mime_type, media_kind, uploaded_by_id
                ) VALUES (%s, %s, %s, %s, 'PHOTO', %s)
            """, [
                case_id,
                submission_id,
                public_url,                         # <— store URL
                f.content_type or None,
                getattr(request.user, 'staff_id', None)
            ])
        saved += 1

    messages.success(request, f"Uploaded {saved} photo(s).")

    # Stay on the same hearing
    if submission_id:
        return redirect(f"/lupon_mem/cases/{case_id}/hearing/?sid={submission_id}")
    return redirect('lupon_mem:case_hearing_schedule', case_id)

# NEWLYYYYYYYYYYYY ADDEDDDDDDDDDDDDDD


def _open_med_attendance_draft(case_id: int) -> int:
    """
    Create (or reuse) a MED-ATT-2025 DRAFT and return submission_id.
    Prefills minimally (safe) using _prefill_minimal_for_case.
    """
    # Reuse latest DRAFT if it exists
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.blotter_case_id=%s
               AND UPPER(f.form_code)='MED-ATT-2025'
               AND UPPER(s.status)='DRAFT'
             ORDER BY s.submission_id DESC
             LIMIT 1
        """, [case_id])
        r = cur.fetchone()
        if r:
            return int(r[0])

        # Resolve form_id for MED-ATT-2025 (must be active)
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)='MED-ATT-2025' AND is_active IS TRUE LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise ValidationError("MED-ATT-2025 is not configured/active.")
        form_id = int(row[0])

        # Create DRAFT
        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT')
            RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # Prefill what we can (best-effort, skip blanks)
        pre = _prefill_minimal_for_case(case_id)
        cur.execute("""
            SELECT kff.field_id, LOWER(kf.field_code)
              FROM kp_form_field kff
              JOIN kp_field kf ON kf.field_id = kff.field_id
             WHERE kff.form_id=%s
        """, [form_id])
        import json as _json
        for field_id, code in cur.fetchall():
            val = pre.get((code or "").lower())
            if val in (None, "", []):
                continue
            cur.execute("""
                INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                VALUES (%s,%s,%s)
                ON CONFLICT (submission_id, field_id)
                DO UPDATE SET value_json=EXCLUDED.value_json
            """, [sid, int(field_id), _json.dumps(val)])

        return sid



@session_login_required
@role_required(*LUPON_ROLES)
def open_mediation_attendance(request: HttpRequest, case_id: int):
    """
    Open (or create) a MED-ATT-2025 draft for this case and jump straight to the builder.
    Mirrors the UX of open_kp16_from_hearing.
    """

    # Prefer going to builder by submission_id if your route supports it;
    # otherwise fall back to builder by form_code.
    try:
        # If your urls.py defines a route that accepts submission_id:
        return redirect(reverse("lupon_mem:form_builder", kwargs={"case_id": case_id}) + f"?submission_id={sid}")
    except Exception:
        # Fallback: open by code (form_builder_by_code will resolve form_id)
        return redirect("lupon_mem:form_builder_by_code", case_id=case_id, form_code="MED-ATT-2025")



# --- Add near your other helpers in views.py ---



def _mark_hearing_held(case_id: int, notice_submission_id: int, outcome: str | None = None) -> bool:
    """
    Marks the hearing (derived from KP-8/KP-12 submission_id) as HELD.
    outcome can be 'SETTLED' or 'NOT SETTLED' (optional).
    Returns True on success.
    """
    try:
        with connection.cursor() as cur:
            # This mirrors your existing dev flow; adjust SQL to your schema if needed.
            # 1) Mark hearing held for this notice_submission_id
            cur.execute("""
                UPDATE blotter_hearing
                   SET held = TRUE, held_at = NOW()
                 WHERE blotter_case_id = %s
                   AND notice_submission_id = %s
            """, [case_id, notice_submission_id])

            # 2) Optionally set the outcome on the case if provided
            if outcome and outcome.upper() == 'SETTLED':
                cur.execute("""
                    UPDATE blotter_case
                       SET settlement_status_id = (SELECT settlement_status_id
                                                     FROM settlement_status
                                                    WHERE UPPER(settlement_status_name)='SETTLED'
                                                    LIMIT 1)
                     WHERE blotter_case_id = %s
                """, [case_id])

        print(f"[auto-held] Marked hearing HELD for case_id={case_id} sid={notice_submission_id} outcome={outcome}")
        return True
    except Exception as e:
        print(f"[auto-held][ERROR] case_id={case_id} sid={notice_submission_id}: {e}")
        return False





# ---------- Resident Lookup (detail) ----------
from django.views.decorators.http import require_GET

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def resident_quick_search(request: HttpRequest):
    """
    GET /lupon_mem/resident/quick-search/?q=term
    Returns top residents for the autocomplete (id, name, purok, address).
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"ok": True, "results": []})

    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              p.person_id AS id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,''))    AS name,
              coalesce(ps.purok_sitio_name,'') AS purok,
              trim(concat_ws(', ',
                    NULLIF(a.street,''),
                    NULLIF(ps.purok_sitio_name,''),
                    NULLIF(a.barangay,''),
                    NULLIF(a.city,'')
              )) AS address
            FROM person p
            LEFT JOIN addresss a   ON a.address_id = p.address_id
            LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
            WHERE
                 p.first_name ILIKE %s
              OR p.last_name  ILIKE %s
              OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
              OR a.street ILIKE %s
            ORDER BY name
            LIMIT 20
            """,
            [like, like, like, like],
        )
        rows = cur.fetchall()

    results = [
        {"id": r[0], "name": (r[1] or "").strip(), "purok": (r[2] or "").strip(), "address": (r[3] or "").strip()}
        for r in rows
    ]
    return JsonResponse({"ok": True, "results": results})


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_GET
def person_lookup(request: HttpRequest):
    """
    GET /lupon_mem/person/lookup/?person_id=123
    -> { ok: true, person: { id, name } }
    """
    pid = (request.GET.get("person_id") or "").strip()
    if not pid.isdigit():
        return JsonResponse({"ok": False, "error": "Invalid person_id."}, status=400)

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              p.person_id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,'')) AS name
            FROM person p
            WHERE p.person_id=%s
            """,
            [int(pid)],
        )
        row = cur.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)

    return JsonResponse({"ok": True, "person": {"id": row[0], "name": (row[1] or "").strip()}})
# ---------- Resident Lookup UI (optional standalone page) ----------
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def resident_lookup(request: HttpRequest):
    """
    A nice standalone page (or embeddable view) to search residents and pick one.
    Supports ?target=INPUT_ID — if provided and the page is opened from a parent form,
    clicking "Use this person" will attempt to fill that INPUT_ID in the opener window.
    """
    target_input = (request.GET.get("target") or "").strip() or None
    return render(request, "lupon_mem/resident_lookup.html", {"target_input": target_input})


#####################

# views.py (helpers)


def _has_med_att_for_notice(case_id: int, notice_submission_id: int) -> bool:
    """
    True if there's a SUBMITTED MED-ATT-2025 that references this hearing notice
    via a field_code 'notice_sid' = notice_submission_id (int or string).
    """
    with connection.cursor() as cur:
        cur.execute("""
            WITH f_att AS (
              SELECT form_id FROM kp_form WHERE UPPER(form_code)='MED-ATT-2025' LIMIT 1
            ),
            fld AS (
              SELECT kf.field_id
              FROM kp_form_field kff
              JOIN kp_field kf ON kf.field_id=kff.field_id
              WHERE kff.form_id=(SELECT form_id FROM f_att)
                AND LOWER(kf.field_code)='notice_sid'
              LIMIT 1
            )
            SELECT 1
            FROM blotter_kp_submission s
            JOIN blotter_kp_answer a
              ON a.submission_id=s.submission_id
            WHERE s.blotter_case_id=%s
              AND s.form_id=(SELECT form_id FROM f_att)
              AND UPPER(s.status)='SUBMITTED'
              AND a.field_id=(SELECT field_id FROM fld)
              AND (a.value_json::text = %s OR a.value_json::text = to_jsonb(%s)::text)
            LIMIT 1
        """, [case_id, str(notice_submission_id), int(notice_submission_id)])
        return cur.fetchone() is not None



@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def generate_settlement_summary(request, case_id: int):
    """
    Manually create MEDx-SETTLED from the latest submitted KP-16, then redirect to the PDF.
    No auto-gen anywhere else.
    """
    # must be SETTLED and have a KP-16
    st = _current_settlement(case_id).upper()
    if st not in ("SETTLED", "AMICABLE SETTLED", "AMICABLE", "AMICABLE SETTLEMENT"):
        messages.error(request, "Case is not settled yet. Record KP-16 first.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    kp16 = _latest_submission_for_codes(case_id, ["KP-16"])
    if not kp16:
        messages.error(request, "No KP-16 found for this case.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    kp16_sid, _, _ = kp16

    try:
        generated = _autogen_settled_summary(case_id=case_id, kp16_submission_id=kp16_sid) or []
    except Exception as e:
        messages.error(request, f"Failed to generate settlement summary: {e}")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    # prefer MED3 > MED2 > MED1 if multiple were created (should be one)
    med_by_code = {item.get("code"): item for item in generated if isinstance(item, dict)}
    for code in ("MED3-SETTLED", "MED2-SETTLED", "MED1-SETTLED"):
        if code in med_by_code:
            sid = med_by_code[code].get("submission_id")
            if sid:
                messages.success(request, f"{code} generated.")
                return redirect(f"/lupon_mem/api/submissions/{sid}/pdf/")

    # generic fallback
    for item in generated:
        try:
            sid = int(item.get("submission_id") if isinstance(item, dict) else item[0])
            return redirect(f"/lupon_mem/api/submissions/{sid}/pdf/")
        except Exception:
            continue

    messages.warning(request, "Summary appears generated, but no file was found.")
    return redirect("lupon_mem:case_detail", case_id=case_id)


from django.db import connection

def _maybe_upsert_hearing_attendance(case_id: int, source_code: str, notice_sid: int,
                                     compl_attended: bool, resp_attended: bool,
                                     settlement: str | None, remarks: str | None) -> None:
    """
    Persist attendance flags for a specific hearing (KP-8/KP-12).
    - UPDATE first; if no row matched, INSERT.
    - Works without unique constraints.
    """
    with connection.cursor() as cur:
        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hearing_attendance (
              blotter_case_id      int      NOT NULL,
              source_code          text     NOT NULL,  -- 'KP-8' / 'KP-12'
              notice_submission_id int      NOT NULL,
              held_at              timestamptz DEFAULT NOW(),
              complainant_attended boolean,
              respondent_attended  boolean,
              settlement_outcome   text,
              remarks              text
            );
        """)

        # Try to UPDATE existing row for (case, source, notice)
        cur.execute("""
            UPDATE hearing_attendance
               SET held_at = NOW(),
                   complainant_attended = %s,
                   respondent_attended  = %s,
                   settlement_outcome   = NULLIF(%s,''),
                   remarks              = NULLIF(%s,'')
             WHERE blotter_case_id = %s
               AND source_code = %s
               AND notice_submission_id = %s
        """, [
            compl_attended, resp_attended,
            settlement or "", remarks or "",
            case_id, source_code, notice_sid
        ])
        if cur.rowcount == 0:
            # No row updated — INSERT a new one
            cur.execute("""
                INSERT INTO hearing_attendance
                  (blotter_case_id, source_code, notice_submission_id,
                   held_at, complainant_attended, respondent_attended,
                   settlement_outcome, remarks)
                VALUES (%s,%s,%s, NOW(), %s,%s, NULLIF(%s,''), NULLIF(%s,''))
            """, [
                case_id, source_code, notice_sid,
                compl_attended, resp_attended,
                settlement or "", remarks or ""
            ])
