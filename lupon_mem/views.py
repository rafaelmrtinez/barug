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

# lupon_mem/views.py  (add these imports near the top)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from lupon_mem.services.case_state import close_case, reopen_case


from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer


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


def _autogen_settled_summary(case_id: int, kp16_submission_id: int):
    """
    Creates MED1/2/3-SETTLED (once) right after KP-16 is submitted.
    Returns a list of {"submission_id", "filename", "download_url", "storage_url"} for the PDFs created.
    Also prints detailed DEBUG lines of raw inputs and final field map.
    """
    import json as _json
    from datetime import date as _date_cls, datetime as _dt

    debug_prefix = "[MED-SETTLED][DEBUG]"
    out = []

    # ---------- figure out which MEDx to create ----------
    with connection.cursor() as cur:
        # count hearings/cncls already held
        cur.execute("""
            SELECT COUNT(*)::int
            FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id=%s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
        """, [case_id])
        held = int(cur.fetchone()[0]) if cur.rowcount else 0
    hearing_num = max(1, min(3, held or 1))  # clamp 1..3
    med_code = {1: "MED1-SETTLED", 2: "MED2-SETTLED", 3: "MED3-SETTLED"}[hearing_num]

    # already have one? (idempotent)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id=%s
              AND UPPER(f.form_code)=UPPER(%s)
              AND UPPER(s.status)='SUBMITTED'
            LIMIT 1
        """, [case_id, med_code])
        exists = cur.fetchone() is not None
    if exists:
        print(f"{debug_prefix} Skipping; {med_code} already exists for case {case_id}.")
        return out

    # ---------- pull case header (raw) ----------
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_num, bc.date_filed, bc.time_filed, bc.incident_desc,
                   COALESCE(ct.complaint_title_name,'') AS complaint_title,
                   COALESCE(cn.case_name,'')           AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
            WHERE bc.blotter_case_id=%s
        """, [case_id])
        r = cur.fetchone() or (None, None, None, None, "", "")
        case_num, date_filed, time_filed, incident_desc, complaint_title, case_nature = r

        cur.execute("""
            SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) AS n
            FROM complainant_case cc JOIN person p ON p.person_id=cc.person_id
            WHERE cc.blotter_case_id=%s ORDER BY n
        """, [case_id])
        complainants = [row[0] for row in cur.fetchall()]

        cur.execute("""
            SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) AS n
            FROM respondent_case rc JOIN person p ON p.person_id=rc.person_id
            WHERE rc.blotter_case_id=%s ORDER BY n
        """, [case_id])
        respondents = [row[0] for row in cur.fetchall()]

    # ---------- prior KP-8/12 schedules (first/second/third notice) ----------
    # We read submitted KP-8 & KP-12, oldest→newest, and collect 3 date/time pairs.
    schedules = []
    with connection.cursor() as cur:
        cur.execute("""
            WITH forms AS (
              SELECT form_id, UPPER(form_code) AS code
              FROM kp_form WHERE UPPER(form_code) IN ('KP-8','KP-12')
            )
            SELECT s.submission_id, f.code, s.submitted_at
            FROM blotter_kp_submission s
            JOIN forms f ON f.form_id=s.form_id
            WHERE s.blotter_case_id=%s AND UPPER(s.status)='SUBMITTED'
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
        """, [case_id])
        kp8_12 = cur.fetchall()

    def _read_pair(form_id, submission_id):
        with connection.cursor() as cur:
            cur.execute("""
                WITH wanted AS (
                  SELECT f.field_id, LOWER(f.field_code) AS code
                  FROM kp_form_field kff
                  JOIN kp_field f ON f.field_id=kff.field_id
                  WHERE kff.form_id=%s
                    AND LOWER(f.field_code) IN ('appearance_date','appearance_time','hearing_date','hearing_time')
                )
                SELECT w.code, a.value_json
                FROM wanted w
                JOIN blotter_kp_answer a
                  ON a.submission_id=%s AND a.field_id=w.field_id
            """, [form_id, submission_id])
            pairs = dict((c or "", a) for c, a in cur.fetchall())
        def clean(v):
            if v is None: return None
            if isinstance(v, str) and len(v)>=2 and v[0]=='"' and v[-1]=='"': return v[1:-1]
            if isinstance(v, dict):
                for k in ("value","text","date","time"):
                    if k in v and v[k]: return v[k]
            return v
        d = clean(pairs.get("hearing_date")) or clean(pairs.get("appearance_date"))
        t = clean(pairs.get("hearing_time")) or clean(pairs.get("appearance_time"))
        return (d, t)

    # need form_id per submission
    schedules_raw = []
    with connection.cursor() as cur:
        for sid_code in kp8_12:
            sid = int(sid_code[0])
            cur.execute("SELECT form_id FROM blotter_kp_submission WHERE submission_id=%s", [sid])
            frow = cur.fetchone()
            if not frow: continue
            form_id = int(frow[0])
            d, t = _read_pair(form_id, sid)
            schedules_raw.append({"submission_id": sid, "date": d, "time": t})
    # take first three
    schedules = schedules_raw[:3]

    # ---------- KP-9 packets (summons + officer's return) ----------
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id=s.form_id
            WHERE s.blotter_case_id=%s AND UPPER(f.form_code)='KP-9' AND UPPER(s.status)='SUBMITTED'
            ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
        """, [case_id])
        kp9_sids = [int(r[0]) for r in cur.fetchall()]

    summons_raw = []
    def _kp9_pick(submission_id):
        # build a best-effort served date and officer return date from month/day/year parts
        with connection.cursor() as cur:
            cur.execute("""
              WITH fld AS (
                SELECT f.field_id, LOWER(f.field_code) AS code
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id=kff.field_id
                WHERE kff.form_id = (SELECT form_id FROM blotter_kp_submission WHERE submission_id=%s)
                  AND LOWER(f.field_code) IN (
                    'summon_date','summon_month','summon_year','summon_time',
                    'offcret_serve_date','offcret_serve_month','offcret_serve_year',
                    'date_offcret','month_offcret','ofcret_year'
                  )
              )
              SELECT code, a.value_json
              FROM fld JOIN blotter_kp_answer a ON a.field_id=fld.field_id AND a.submission_id=%s
            """, [submission_id, submission_id])
            dd = dict((c or "", a) for c, a in cur.fetchall())
        def c(v):
            if v is None: return None
            if isinstance(v, str) and len(v)>=2 and v[0]=='"' and v[-1]=='"': return v[1:-1]
            if isinstance(v, dict):
                for k in ("value","text","date","time"):
                    if k in v and v[k]: return v[k]
            return v
        def join_mdy(m, d, y):
            m = (m or "").strip(); d = (d or "").strip(); y = (y or "").strip()
            return " ".join(x for x in [m, d + ("," if y else ""), y] if x).replace(" ,", ",")
        served = join_mdy(c(dd.get("summon_month")), c(dd.get("summon_date")), c(dd.get("summon_year")))
        served_time = c(dd.get("summon_time"))
        ofc = join_mdy(c(dd.get("offcret_serve_month")) or c(dd.get("month_offcret")),
                       c(dd.get("offcret_serve_date"))  or c(dd.get("date_offcret")),
                       c(dd.get("offcret_serve_year"))  or c(dd.get("ofcret_year")))
        return {"served": served, "served_time": served_time, "officer_return": ofc}

    for sid in kp9_sids[:3]:
        summons_raw.append(_kp9_pick(sid))

    # ---------- KP-16 raw (settlement) ----------
    with connection.cursor() as cur:
        cur.execute("""
          WITH flds AS (
            SELECT f.field_id, LOWER(f.field_code) AS code
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id=kff.field_id
            WHERE kff.form_id = (SELECT form_id FROM blotter_kp_submission WHERE submission_id=%s)
          )
          SELECT code, a.value_json
          FROM flds JOIN blotter_kp_answer a ON a.field_id=flds.field_id AND a.submission_id=%s
        """, [kp16_submission_id, kp16_submission_id])
        kp16_pairs = dict((c or "", a) for c, a in cur.fetchall())

    def clean(v):
        if v is None: return None
        if isinstance(v, str) and len(v)>=2 and v[0]=='"' and v[-1]=='"': return v[1:-1]
        if isinstance(v, dict):
            for k in ("value","text","date","time"):
                if k in v and v[k]: return v[k]
        return v

    settlement_statement = clean(kp16_pairs.get("settlement_statement"))
    dt_entered          = clean(kp16_pairs.get("date_entered"))
    tm_filed            = clean(kp16_pairs.get("time_filed"))

    # helpful pretty date+time
    def dt_join(d, t):
        if d and t: return f"{d} {t}"
        return d or t or ""

    # ---------- debug: raw ----------
    print(f"{debug_prefix} case_id={case_id} hearing_num={hearing_num} → {med_code}")
    print(f"{debug_prefix} RAW header:", {
        "case_num": case_num, "date_filed": str(date_filed), "time_filed": str(time_filed),
        "complaint_title": complaint_title, "case_nature": case_nature,
        "complainants": complainants, "respondents": respondents
    })
    print(f"{debug_prefix} RAW schedules (KP-8/12 oldest→newest):", schedules)
    print(f"{debug_prefix} RAW summons(KP-9 oldest→newest):", summons_raw)
    print(f"{debug_prefix} RAW KP-16:", {
        "settlement_statement": settlement_statement,
        "date_entered": dt_entered, "time_filed": tm_filed
    })

    # ---------- build a flexible field map (only fill what exists on the target MEDx) ----------
    # We'll pull the MEDx's actual field_codes so we never try to write unknown fields.
    with connection.cursor() as cur:
        cur.execute("""
            SELECT f.form_id FROM kp_form f WHERE UPPER(f.form_code)=UPPER(%s) LIMIT 1
        """, [med_code])
        med_form_id = int(cur.fetchone()[0])

        cur.execute("""
            SELECT LOWER(kf.field_code) AS code, kf.field_id
            FROM kp_form_field kff
            JOIN kp_field kf ON kf.field_id=kff.field_id
            WHERE kff.form_id=%s
        """, [med_form_id])
        med_fields = {code: fid for code, fid in cur.fetchall()}

    # values (by code) – we only keep keys that exist in med_fields
    values_by_code = {}

    def put(code, val):
        c = (code or "").lower()
        if c in med_fields and val not in (None, "", "null"):
            values_by_code[c] = val

    # header
    put("case_num", case_num)
    if isinstance(date_filed, (_date_cls, _dt)):
        put("dt_filed", date_filed.isoformat())
    else:
        put("dt_filed", str(date_filed) if date_filed else None)

    put("complainant_name", ", ".join(complainants))
    put("respondent_name",  ", ".join(respondents))
    put("complaint_title", complaint_title)
    put("case_nature",    case_nature)

    # notices (from KP-8/12)
    if schedules:
        d0, t0 = schedules[0].get("date"), schedules[0].get("time")
        d1, t1 = (schedules[1].get("date"), schedules[1].get("time")) if len(schedules)>1 else (None, None)
        d2, t2 = (schedules[2].get("date"), schedules[2].get("time")) if len(schedules)>2 else (None, None)
        put("first_notice_dt",  dt_join(d0, t0))
        put("second_notice_dt", dt_join(d1, t1))
        put("third_notice_dt",  dt_join(d2, t2))
        # some MEDx variants use codes 'first_hearing_dt'... – set them too if present
        put("first_hearing_dt",  dt_join(d0, t0))
        put("second_hearing_dt", dt_join(d1, t1))
        put("third_hearing_dt",  dt_join(d2, t2))

    # summons (KP-9)
    if summons_raw:
        s0 = summons_raw[0] if len(summons_raw)>=1 else {}
        s1 = summons_raw[1] if len(summons_raw)>=2 else {}
        s2 = summons_raw[2] if len(summons_raw)>=3 else {}
        put("first_summon_dt",  dt_join(s0.get("served"), s0.get("served_time")))
        put("officer_return_dt", s0.get("officer_return"))
        put("second_summon_dt", dt_join(s1.get("served"), s1.get("served_time")))
        put("officer_return_dt2", s1.get("officer_return"))
        put("third_summon_dt",  dt_join(s2.get("served"), s2.get("served_time")))
        put("third_offret_dt",  s2.get("officer_return"))

    # actions: confrontation / settlement
    # 1st/2nd/3rd confrontation date&time → use the *latest HELD* entry (best-effort) or first/second/third if you track separately.
    with connection.cursor() as cur:
        cur.execute("""
            SELECT to_char(cpt.date_processed,'YYYY-MM-DD') AS d,
                   to_char(cpt.date_processed,'HH24:MI')    AS t
            FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id=%s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
            ORDER BY cpt.date_processed ASC
        """, [case_id])
        held_rows = cur.fetchall()
    if held_rows:
        idx = min(len(held_rows), 3) - 1  # zero-based
        d_held, t_held = held_rows[idx]
        if idx == 0: put("first_conf_dt",  dt_join(d_held, t_held))
        if idx == 1: put("second_conf_dt", dt_join(d_held, t_held))
        if idx == 2: put("third_conf_dt",  dt_join(d_held, t_held))

    # settlement
    put("settlement_dt", dt_join(dt_entered, tm_filed))
    # agreement text – MED1 uses "Text Box 1", MED2/3 use "point_agreement"/"point_of_agreement"
    put("text box 1",        settlement_statement)
    put("point_agreement",   settlement_statement)
    put("point_of_agreement", settlement_statement)

    # monitors – safe defaults
    put("monitoring_date", _date_cls.today().isoformat())

    # print final map we will write (field_code → value)
    print(f"{debug_prefix} FINAL FIELD MAP ({med_code}):")
    for k, v in values_by_code.items():
        print(f"{debug_prefix}   {k} = {v}")

    # ---------- write submission + answers ----------
    with transaction.atomic():
        with connection.cursor() as cur:
            # create the submission in DRAFT
            cur.execute("""
                INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
                SELECT %s, form_id, 'DRAFT'
                FROM kp_form WHERE UPPER(form_code)=UPPER(%s)
                RETURNING submission_id
            """, [case_id, med_code])
            med_sid = int(cur.fetchone()[0])

            # insert answers (only for codes that exist on the form)
            for code, val in values_by_code.items():
                field_id = med_fields[code]
                cur.execute("""
                    INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (submission_id, field_id)
                    DO UPDATE SET value_json=EXCLUDED.value_json
                """, [med_sid, field_id, _json.dumps(val)])

            # mark submitted
            cur.execute("UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s",
                        [med_sid])

    # ---------- render + upload, return a download link ----------
    try:
        pdf_bytes, med_filename = render_final_pdf(submission_id=med_sid)
    except Exception as e:
        print(f"{debug_prefix} render_final_pdf failed for {med_code} sid={med_sid}: {e}")
        return out

    # store to supabase (best-effort; mimic your KP-16 branch)
    bucket = getattr(settings, "SUPABASE_BUCKET", "documents")
    path = f"blotter/{case_id}/{med_filename}"
    storage_url = None
    try:
        supabase.storage.from_(bucket).upload(path, pdf_bytes,
            {"contentType":"application/pdf","upsert":"true"})
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
    except Exception:
        storage_url = None

    # local download url
    local_download = reverse("lupon_mem:submission_pdf", args=[med_sid])
    out.append({
        "submission_id": med_sid,
        "filename": med_filename,
        "download_url": local_download,
        "storage_url": storage_url,
        "code": med_code,              # ← add this
    })

    print(f"{debug_prefix} CREATED {med_code} sid={med_sid} file={med_filename}")
    return out



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





from django.db import connection

def _hearing_gate(case_id: int) -> dict:
    """
    Gate computed entirely from fn_case_mediation_hearings(case_id).
    Returns:
      {
        'hearings_held': int,                 # rows with hearing_held=true or held_at not null
        'hearings_set': int,                  # total rows from the TVF
        'latest_notice_submitted_at': datetime|None,
        'latest_notice_submission_id': int|None,
        'latest_notice_code': str|None,       # 'KP-8' or 'KP-12'
        'latest_notice_outstanding': bool,    # latest row NOT marked held
        'settlement_name': str|None,
        'can_issue_notice': bool,
        'reason': str,
        'limit_reached': bool,                # 3 held already
      }
    """
    rows = []
    with connection.cursor() as cur:
        # 1) Pull per-hearing rows (one per KP-8/12)
        cur.execute("""
            SELECT
              hearing_no, source, notice_sid, notice_created_at,
              hearing_date, hearing_time,
              hearing_held, held_at, held_remarks,
              complainant_attended, respondent_attended,
              settlement_outcome
            FROM fn_case_mediation_hearings(%s)
            ORDER BY notice_created_at ASC NULLS LAST, notice_sid ASC
        """, [case_id])
        rows = cur.fetchall()

        # 2) Settlement text (same as before)
        cur.execute("""
            SELECT COALESCE(ss.settlement_status_name,'PENDING') AS name
            FROM blotter_case bc
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        st = cur.fetchone()
        settlement_name = (st[0] if st else None)

    # Columns (index map from SELECT above)
    IDX = {
        "hearing_no": 0, "source": 1, "notice_sid": 2, "notice_created_at": 3,
        "hearing_date": 4, "hearing_time": 5,
        "hearing_held": 6, "held_at": 7, "held_remarks": 8,
        "compl_att": 9, "resp_att": 10, "settlement_outcome": 11,
    }

    hearings_set = len(rows)
    hearings_held = sum(1 for r in rows if (bool(r[IDX["hearing_held"]]) or r[IDX["held_at"]] is not None))

    # Latest = the last row in our ORDER BY (ASC), or compute max explicitly
    latest_row = rows[-1] if rows else None
    latest_at  = latest_row[IDX["notice_created_at"]] if latest_row else None
    latest_sid = int(latest_row[IDX["notice_sid"]]) if latest_row else None
    latest_code= latest_row[IDX["source"]] if latest_row else None

    # “Outstanding” means the latest hearing isn't marked HELD yet
    latest_outstanding = False
    if latest_row:
        latest_outstanding = not (bool(latest_row[IDX["hearing_held"]]) or latest_row[IDX["held_at"]] is not None)

    # Last held timestamp across all hearings (for info/consistency)
    last_held_at = None
    if rows:
        held_times = [r[IDX["held_at"]] for r in rows if r[IDX["held_at"]] is not None]
        last_held_at = max(held_times) if held_times else None

    # Same gating rules you had
    settlement_up = (settlement_name or '').strip().upper()
    settlement_pending = settlement_up in ('PENDING', 'NOT SETTLED', 'UNSET', 'FOR MEDIATION', 'FOR CONCILIATION')

    limit_reached = hearings_held >= 3
    can_issue = (not limit_reached) and (not latest_outstanding) and settlement_pending

    reason = ""
    if limit_reached:
        reason = "Limit reached: 3 hearings already held (proceed to Arbitration/CFA)."
    elif latest_outstanding:
        reason = "There is a scheduled hearing not yet marked HELD."
    elif not settlement_pending:
        reason = f"Settlement is “{settlement_name}” (set to Pending/Not Settled to schedule another)."

    return {
        "hearings_held": int(hearings_held or 0),
        "hearings_set": int(hearings_set or 0),
        "latest_notice_submitted_at": latest_at,
        "latest_notice_submission_id": latest_sid,
        "latest_notice_code": latest_code,
        "latest_notice_outstanding": bool(latest_outstanding),
        "settlement_name": settlement_name,
        "can_issue_notice": bool(can_issue),
        "reason": reason,
        "limit_reached": bool(limit_reached),
    }



from typing import Dict
from datetime import date as _date
from django.db import connection

def _prefill_minimal_for_case(case_id: int) -> Dict[str, str]:
    """
    Minimal, safe prefill mapping by *field_code* that works well for KP-16 and MEDx-SETTLED.
    Pulls common parties, case no., 'purpose', and a few generic dates.

    Fields produced (aliases included):
      - complainants, complainants_two
      - respondents,  respondents_two
      - brgy_case_num, brgy_case_number, case_num
      - purpose
      - incident_date (ISO), incident_time (HH:MM)
      - punong_barangay / brgy_capt / brgy_captain / chairman
      - date_created / month_created / year_received
      - current_date / current_month / current_year
      - settlement_statement, date_filed, time_filed, date_entered, month_entered, year_entered
    """
    with connection.cursor() as cur:
        # ── Case header
        cur.execute(
            """
            SELECT
              bc.blotter_case_num,
              bc.incident_desc,
              bc.incident_date,
              bc.incident_time,
              COALESCE(ct.complaint_title_name,'') AS complaint_title,
              COALESCE(cn.case_name,'')           AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
            WHERE bc.blotter_case_id = %s
            """,
            [case_id],
        )
        row = cur.fetchone() or (None, None, None, None, "", "")
        case_num, incident_desc, incident_date, incident_time, complaint_title, case_nature = row

        # ── Parties (use full name: first, middle, last, suffix; trim spacing)
        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
                   ) AS name
            FROM complainant_case cc
            JOIN person p ON p.person_id = cc.person_id
            WHERE cc.blotter_case_id = %s
            ORDER BY name
            """,
            [case_id],
        )
        complainants = ", ".join([r[0] for r in cur.fetchall()])

        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
                   ) AS name
            FROM respondent_case rc
            JOIN person p ON p.person_id = rc.person_id
            WHERE rc.blotter_case_id = %s
            ORDER BY name
            """,
            [case_id],
        )
        respondents = ", ".join([r[0] for r in cur.fetchall()])

        # ── PB (Punong Barangay / Barangay Captain)
        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
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
        punong_barangay = (row_pb[0].strip() if row_pb and row_pb[0] else "") or "LOURDES RAMIREZ"

    # ── Date helpers (use "today" fallbacks)
    today = _date.today()
    today_iso  = today.isoformat()
    today_mon  = today.strftime("%B")
    today_year = str(today.year)

    def _hm(t) -> str | None:
        try:
            return t.strftime("%H:%M")
        except Exception:
            return None

    # ── Purpose (Complaint Title - Case Nature)
    purpose = f"{(complaint_title or '').strip()} - {(case_nature or '').strip()}".strip(" -")

    return {
        # Parties
        "complainants": complainants,
        "respondents": respondents,
        "complainants_two": complainants,
        "respondents_two": respondents,

        # Case no. aliases
        "brgy_case_num": case_num or "",
        "brgy_case_number": case_num or "",
        "case_num": case_num or "",

        # Purpose + incident
        "purpose": purpose,
        "incident_date": (incident_date.isoformat() if hasattr(incident_date, "isoformat") else None) or today_iso,
        "incident_time": _hm(incident_time) or None,

        # Captain / signatures (aliases)
        "punong_barangay": punong_barangay,
        "brgy_capt": punong_barangay,
        "brgy_captain": punong_barangay,
        "chairman": punong_barangay,

        # Generic current stamps
        "date_created": today_iso,
        "month_created": today_mon,
        "year_received": today_year,
        "current_date":  today_iso,
        "current_month": today_mon,
        "current_year":  today_year,

        # KP-16 friendly defaults
        "settlement_statement": (incident_desc or "").strip() or "Amicable settlement reached.",
        "date_filed": today_iso,
        "time_filed": _hm(incident_time) or "14:00",
        "date_entered": today_iso,
        "month_entered": today_mon,
        "year_entered": today_year,
    }


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


# views.py
from datetime import date as _date_cls, datetime as _dt_cls
from typing import Any, Dict, Optional
import json

from django.db import connection
from django.http import HttpResponseBadRequest
from django.shortcuts import render


def _slice_until_code(fields_with_values, stop_code: Optional[str]):
    if not stop_code:
        return fields_with_values
    stop_code_l = (stop_code or "").strip().lower()
    out = []
    for tup in fields_with_values:
        out.append(tup)
        code = (tup[6] or "").strip().lower()
        if code == stop_code_l:
            break
    return out




# views.py (only wiring to services; same behavior)
from lupon_mem.services.form_builder_service import (
    fetch_header, fetch_fields, fetch_saved_answers, fetch_case_core,
    resolve_incident_address, fetch_party_names, fetch_party_json,
    fetch_punong_barangay, build_prefills, apply_answers_and_prefills,
    find_page2_index, slice_until_code, compute_ui_flags
)



# views.py (only wiring to services; same behavior)
from lupon_mem.services.form_builder_service import (
    fetch_header, fetch_fields, fetch_saved_answers, fetch_case_core,
    resolve_incident_address, fetch_party_names, fetch_party_json,
    fetch_punong_barangay, build_prefills, apply_answers_and_prefills,
    find_page2_index, slice_until_code, compute_ui_flags
)

@session_login_required
@nocache
@role_required(*LUPON_ROLES)
def form_builder(request, case_id: int, form_id: int = None, submission_id: int = None):
    with connection.cursor() as cur:
        # Header
        fid, hdr_norm, form_code = fetch_header(cur, form_id, submission_id)

        # Fields + saved answers
        fields  = fetch_fields(cur, fid)
        answers = fetch_saved_answers(cur, submission_id)

        # Case core
        (case_num, incident_desc, incident_date, incident_time,
         incident_loc_raw, date_filed,
         complaint_title_name, case_nature_name, blotter_report_id) = fetch_case_core(cur, case_id)

        # Incident location (fallback to report address)
        incident_addr_text = resolve_incident_address(cur, blotter_report_id)
        incident_loc = (incident_loc_raw or incident_addr_text or "") or None

        # Parties (names + JSON)
        cmps, resps = fetch_party_names(cur, case_id)
        complainants_json, respondents_json = fetch_party_json(cur, case_id)

        parties_complainant = ", ".join([x.strip() for x in cmps if x.strip()])
        parties_respondent  = ", ".join([x.strip() for x in resps if x.strip()])
        first_respondent    = (resps[0].strip() if resps else "")

        # PB
        punong_barangay = fetch_punong_barangay(cur)

        # Prefills
        prefill_by_label, prefill_by_code, *_unused_dates = build_prefills(
            case_num=case_num,
            incident_desc=incident_desc,
            incident_date=incident_date,
            incident_time=incident_time,
            incident_loc=incident_loc,
            date_filed=date_filed,
            complaint_title_name=complaint_title_name,
            case_nature_name=case_nature_name,
            punong_barangay=punong_barangay,
            parties_complainant=parties_complainant,
            parties_respondent=parties_respondent,
            first_respondent=first_respondent,
        )

        # Apply values
        fields_with_values = apply_answers_and_prefills(
            fields, answers, prefill_by_label, prefill_by_code,
            form_id=fid, submission_id=submission_id, form_code=form_code
        )

    # Page 2 split marker
    page2_index = find_page2_index(fields_with_values)

    # Optional stop-at
    stop_code = request.GET.get("show_until")
    if not stop_code and str(fid) == "7":
        stop_code = "solutions_seeked"
    if stop_code:
        fields_with_values = slice_until_code(fields_with_values, stop_code)

    # UI flags
    flags = compute_ui_flags(form_code)

    # KP-9 minimal filter (exactly same as before)
    if flags["kp9_ui_minimal"]:
        allowed_codes = {"summon_date", "summon_time"}
        fields_with_values = [item for item in fields_with_values if ((item[6] or "").strip().lower() in allowed_codes)]
        page2_index = None

    # KP-15 minimal filter (show up to award_description)
    if flags["kp15_ui_minimal"]:
        fields_with_values = slice_until_code(fields_with_values, "award_description")
        page2_index = None

    return render(
        request,
        "lupon_mem/form_builder.html",
        {
            "case_id": case_id,
            "submission_id": submission_id,
            "form_id": fid,              # numeric (e.g., 25)
            "form_code": form_code,      # string, e.g., "KP-23"
            "header": hdr_norm,
            "fields": fields_with_values,
            "answers": answers,
            "page2_index": page2_index,
            "stop_code": stop_code,
            **flags,
            "complainants": complainants_json,
            "respondents": respondents_json,
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



# Helper kp17
def _insert_kp17_meta(submission_id: int, case_id: int, request) -> None:
    """
    Extracts who filed KP-17 from POST and inserts meta via SQL function.
    Expects:
      - 'repudiating_party': 'COMPLAINANT' | 'RESPONDENT'
      - 'repudiating_person_id': person_id of the filer (must match the chosen side)
    """
    from django.db import connection

    party = (request.POST.get("repudiating_party") or "").strip().upper()
    person_id_txt = (request.POST.get("repudiating_person_id") or "").strip()
    if not party or not person_id_txt.isdigit():
      # Nothing provided → skip (or raise, depending on your policy)
      return

    party_person_id = int(person_id_txt)

    # If a staff user is logged in, pass staff_id; else None
    created_by_staff = getattr(getattr(request.user, "staff", None), "staff_id", None)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT insert_kp17_repudiation_meta(%s,%s,%s,%s)",
            [submission_id, party, party_person_id, created_by_staff]
        )


# --- AJAX: submit & generate PDF ---
@role_required(*LUPON_ROLES)
@session_login_required
def submit_form(request: HttpRequest):
    """
    Save any posted answers, render PDF, upload, mark submitted, then allow the
    form-specific handler to persist its auto-computed answers via a universal hook.

    Extras retained:
      • KP-23: record 'who filed' meta (party/person) via function.
      • KP-16: set case status SETTLED, optional MED summary generation, auto-mark hearing HELD.
    """
    import json as _json
    import json
    from datetime import datetime as _dt
    from django.db import transaction
    from django.urls import reverse
    from django.http import JsonResponse
    from django.conf import settings
    from django.contrib import messages
    from zoneinfo import ZoneInfo

    log = logging.getLogger(__name__)

    # ---------- Parse body ----------
    try:
        data = _json.loads(request.body.decode())
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON body."}, status=400)

    try:
        submission_id = int(data["submission_id"])
        case_id       = int(data["case_id"])
    except Exception:
        return JsonResponse({"ok": False, "error": "Missing or invalid submission_id/case_id."}, status=400)

    # ---------- Persist latest posted answers (generic for ALL forms) ----------
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

    # ---------- Render PDF ----------
    try:
        # Uses your per-form handlers internally
        from lupon_mem.services.form_renderer import render_final_pdf
        pdf_bytes, filename = render_final_pdf(submission_id=submission_id)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception:
        log.exception("submit_form render_final_pdf failed")
        return JsonResponse({"ok": False, "error": "Failed to generate PDF."}, status=500)

    # ---------- Upload to Supabase (best-effort) ----------
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

    # ---------- Mark SUBMITTED ----------
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

    # ---------- Determine form_code + form_id ----------
    row_fc = None
    form_id_of_submission = None
    form_code = None
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(kf.form_code), s.form_id
                  FROM blotter_kp_submission s
                  JOIN kp_form kf ON kf.form_id = s.form_id
                 WHERE s.submission_id=%s
            """, [submission_id])
            row_fc = cur.fetchone()
            if row_fc:
                form_code = str(row_fc[0])
                form_id_of_submission = int(row_fc[1])
    except Exception:
        log.exception("submit_form failed to lookup form_code (submission_id=%s)", submission_id)

    # ---------- Universal: let the specific handler persist its computed answers ----------
    try:
        if form_code and form_id_of_submission:
            # Rebuild the exact name→value map used to render the PDF (so persisted values match the PDF)
            from lupon_mem.services.forms import get_handler
            handler = get_handler(form_code)
            # Many handlers expose build_name_value_map(form_id, submission_id)
            out_map = {}
            try:
                out_map = handler.build_name_value_map(form_id_of_submission, submission_id) or {}
            except Exception:
                # If a specific handler doesn’t implement it, fall back to generic answers mapping
                from lupon_mem.services.form_shared import answers_to_names_strict
                out_map = answers_to_names_strict(form_id_of_submission, submission_id)

            # Give the handler a chance to persist its auto-computed values
            if hasattr(handler, "persist_computed"):
                handler.persist_computed(
                    form_id=form_id_of_submission,
                    submission_id=submission_id,
                    case_id=case_id,
                    out_map=out_map,
                )
    except Exception:
        log.exception("persist_computed hook failed (submission_id=%s)", submission_id)
        # Non-fatal; continue

    # ---------- KP-23: record who filed (party/person) ----------
    try:
        if form_code and form_code.upper() == "KP-23":
            meta = data.get("meta") or {}
            party_raw  = (data.get("filed_by_party") or meta.get("filed_by_party") or "").strip().upper()
            person_raw = (data.get("filed_by_person_id") or meta.get("filed_by_person_id"))

            if party_raw not in ("COMPLAINANT", "RESPONDENT"):
                return JsonResponse({"ok": False,
                                     "error": "For KP-23, 'filed_by_party' must be COMPLAINANT or RESPONDENT."},
                                    status=400)
            try:
                party_person_id = int(person_raw)
            except Exception:
                return JsonResponse({"ok": False,
                                     "error": "For KP-23, 'filed_by_person_id' must be a valid person_id integer."},
                                    status=400)

            staff_id = (request.session.get("auth") or {}).get("staff_id")

            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT insert_kp23_filer_meta(%s,%s,%s,%s)",
                        [submission_id, party_raw, party_person_id, staff_id]
                    )
            except Exception as e:
                msg = str(e)
                if "P6310" in msg:
                    return JsonResponse({"ok": False, "error": "Submission is not KP-23."}, status=400)
                if "P6311" in msg:
                    return JsonResponse({"ok": False, "error": "Submission not found or case mismatch."}, status=400)
                if "P6312" in msg:
                    return JsonResponse({"ok": False, "error": "Invalid party type for KP-23."}, status=400)
                if "P6313" in msg:
                    return JsonResponse({"ok": False, "error": "Selected person is not on that side for this case."}, status=400)
                if "P6314" in msg:
                    return JsonResponse({"ok": False, "error": "Filer meta already exists for this submission."}, status=400)
                log.exception("submit_form KP-23 meta insert failed (submission_id=%s)", submission_id)
                return JsonResponse({"ok": False, "error": "Failed to record KP-23 filer."}, status=500)

            # Optional: also save a display string to a TEXT field if present (kp23_filed_by)
            try:
                filed_by_text = f"{party_raw.title()} — person_id #{party_person_id}"
                if form_id_of_submission:
                    with connection.cursor() as cur:
                        cur.execute("""
                            SELECT f.field_id
                              FROM kp_form_field kff
                              JOIN kp_field f ON f.field_id = kff.field_id
                             WHERE kff.form_id = %s AND LOWER(f.field_code) = 'kp23_filed_by'
                             LIMIT 1
                        """, [int(form_id_of_submission)])
                        row = cur.fetchone()
                    if row:
                        fb_field_id = int(row[0])
                        with transaction.atomic():
                            with connection.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (submission_id, field_id)
                                    DO UPDATE SET value_json = EXCLUDED.value_json
                                """, [submission_id, fb_field_id, json.dumps(filed_by_text)])
            except Exception:
                log.warning("submit_form KP-23: failed to persist kp23_filed_by display text", exc_info=True)
    except Exception:
        log.exception("submit_form KP-23 filer block error (submission_id=%s)", submission_id)
        return JsonResponse({"ok": False, "error": "KP-23 filer recording failed unexpectedly."}, status=500)

    # ---------- KP-16: set case SETTLED on submit ----------
    extra_files = []
    try:
        if form_code and form_code.upper() == "KP-16":
            staff_id = (request.session.get("auth") or {}).get("staff_id")
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Settled via KP-16', staff_id])
            messages.success(request, "Settlement finalized (KP-16 submitted).")
    except Exception:
        log.exception("Failed to set case SETTLED on KP-16 submit")

    # ---------- KP-16: optional MEDx settled summary (feature-flag) ----------
    try:
        if form_code and form_code.upper() == "KP-16" and getattr(settings, "LUPON_AUTOGEN_MEDX", False):
            from lupon_mem.services.med_settled import _autogen_settled_summary
            extra_files = _autogen_settled_summary(case_id=case_id, kp16_submission_id=submission_id) or []
    except Exception as e:
        print("[MED-SETTLED][DEBUG] auto generation failed:", e)

    # ---------- KP-16: auto-mark hearing as HELD when triggered from hearing page ----------
    try:
        if form_code and form_code.upper() == "KP-16":
            sid = request.session.get("auto_mark_hearing_after_kp16_sid")
            sid_case = request.session.get("auto_mark_hearing_case_id")
            if sid and sid_case and int(sid_case) == int(case_id):
                try:
                    with connection.cursor() as cur:
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
                request.session.pop("auto_mark_hearing_after_kp16_sid", None)
                request.session.pop("auto_mark_hearing_case_id", None)
                request.session.modified = True
    except Exception as e:
        log.exception("submit_form post-KP16 auto-held hook error: %s", e)

    # ---------- Local download url (always works) ----------
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


def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()


# --- Dashboard ---
@session_login_required
@role_required(*LUPON_ROLES)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    lupon_mem_dashboard_service=Provide[AppContainer.lupon_mem_dashboard_service],
):
    user_role = _auth_role_name(request)

    kpis = {
        "ongoing_cases": 0,
        "open_cases": None,
        "total_case_settled": 0,
        "total_case_settled_delta": None,
        "total_case_unsettled": 0,
        "total_case_unsettled_delta": None,
        "settlement_rate": 0,
    }

    dashboard_json = None

    try:
        payload = lupon_mem_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json") 
    except Exception as exc:
        print("Error fetching lupon mem dashboard KPIs:", exc)

    return render(
        request,
        "lupon_mem/dashboard.html",
        {
            'page_path' : f'{user_role} / Dashboard',
            'page_title' : 'Dashboard',
            'kpis': kpis,
            'dashboard_json': dashboard_json,
            'today': datetime.now().strftime("%B %d, %Y"),
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
    Attach-a-form chooser with gates:
      • Block when latest KP-9 attendance not marked (unless MED-ATT-2025 intent)
      • Block when there is an outstanding hearing notice (unless MED-ATT-2025 intent)

    Shows only forms valid for the case's current stage, covering KP-7..KP-25.
    """
    from django.db import connection
    from django.utils import timezone
    from datetime import timedelta
    from django.contrib import messages

    # ---- read intent flags from query ----
    requested_code = (request.GET.get("code") or "").upper().strip()
    allow_med_att  = (
        requested_code == "MED-ATT-2025"
        or (request.GET.get("allow_med_att") == "1")
        or (request.GET.get("from") == "hearing")
    )

    # ---- helpers ----
    def _one_val(sql, params=None):
        with connection.cursor() as c:
            c.execute(sql, params or [])
            r = c.fetchone()
            return r[0] if r else None

    def _row(sql, params=None):
        with connection.cursor() as c:
            c.execute(sql, params or [])
            return c.fetchone()

    def _rows(sql, params=None):
        with connection.cursor() as c:
            c.execute(sql, params or [])
            return c.fetchall()

    # ---- hearing gate (your existing util) ----
    gate = _hearing_gate(case_id)
    latest_notice_outstanding = bool(gate.get("latest_notice_outstanding"))

    # ---- case snapshot (settlement text) ----
    case_row = _row("""
        SELECT bc.settlement_status_id, COALESCE(UPPER(ss.settlement_status_name), '')
        FROM blotter_case bc
        LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
        WHERE bc.blotter_case_id=%s
    """, [case_id])
    settlement_status_name = (case_row[1] or '') if case_row else ''

    # ---- submitted codes map (your existing util) ----
    submitted = _submitted_codes(case_id)

    def _has(code: str) -> bool:
        return bool(submitted.get(code.upper()))

    # ---- latest KP-9 attendance & NO SHOW counters ----
    latest_kp9 = _row("""
        WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
        SELECT a.status, COALESCE(UPPER(a.no_show_party), '')
        FROM kp9_attendance a
        JOIN blotter_kp_submission s ON s.submission_id = a.submission_id
        WHERE s.blotter_case_id = %s AND s.form_id = (SELECT form_id FROM f)
        ORDER BY a.marked_at DESC NULLS LAST, s.submission_id DESC
        LIMIT 1
    """, [case_id])
    latest_att_status = (latest_kp9[0] or '').upper() if latest_kp9 else None
    latest_att_party  = (latest_kp9[1] or '') if latest_kp9 else ''

    no_show_counts = dict(_rows("""
        WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
        SELECT COALESCE(UPPER(a.no_show_party), 'UNKNOWN') AS party, COUNT(*)
        FROM kp9_attendance a
        JOIN blotter_kp_submission s ON s.submission_id = a.submission_id
        WHERE s.blotter_case_id=%s AND a.status ILIKE 'NO SHOW'
        GROUP BY COALESCE(UPPER(a.no_show_party), 'UNKNOWN')
    """, [case_id]) or [])
    repeated_ns_compl = (no_show_counts.get('COMPLAINANT', 0) >= 2) or (no_show_counts.get('BOTH', 0) >= 2)
    repeated_ns_resp  = (no_show_counts.get('RESPONDENT', 0)  >= 2) or (no_show_counts.get('BOTH', 0) >= 2)

    # ---- KP-9 counts & pending attendance ----
    summons_count = int(_one_val("""
        WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
        SELECT COUNT(*) FROM blotter_kp_submission
        WHERE blotter_case_id=%s AND form_id=(SELECT form_id FROM f)
    """, [case_id]) or 0)

    kp9_pending_count = int(_one_val("""
        WITH f AS (SELECT form_id FROM kp_form WHERE UPPER(form_code)='KP-9' LIMIT 1)
        SELECT COUNT(*)
        FROM blotter_kp_submission s
        WHERE s.blotter_case_id=%s
          AND s.form_id=(SELECT form_id FROM f)
          AND NOT EXISTS (SELECT 1 FROM kp9_attendance a WHERE a.submission_id = s.submission_id)
    """, [case_id]) or 0)
    pending_summons = (summons_count > 0) and (kp9_pending_count > 0)

    # ---- hearings held (from your gate) ----
    hearings_held = int(gate.get("hearings_held") or 0)
    notice_outstanding = latest_notice_outstanding

    # ---- KP-16 / KP-17 window & execution gates ----
    kp16_row = _row("""
        SELECT s.submission_id, s.submitted_at
        FROM blotter_kp_submission s
        JOIN kp_form kf ON kf.form_id = s.form_id
        WHERE s.blotter_case_id=%s AND UPPER(kf.form_code)='KP-16'
        ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
        LIMIT 1
    """, [case_id])
    has_kp16 = bool(kp16_row)
    kp16_signed_at = kp16_row[1] if kp16_row else None

    kp17_exists = bool(_one_val("""
        SELECT 1
        FROM blotter_kp_submission s
        JOIN kp_form kf ON kf.form_id = s.form_id
        WHERE s.blotter_case_id=%s AND UPPER(kf.form_code)='KP-17'
        LIMIT 1
    """, [case_id]))

    today = timezone.now()
    within_repudiation_window = False
    final_and_executory = False
    if has_kp16 and kp16_signed_at:
        try:
            dt_local = timezone.localtime(kp16_signed_at)
        except Exception:
            dt_local = kp16_signed_at
        days_since = (today - dt_local).days
        within_repudiation_window = (days_since <= 10) and not kp17_exists
        final_and_executory = (days_since > 10) and not kp17_exists

    # Expose KP-23 when final & executory; handler should still verify NON-COMPLIANCE.
    can_kp23 = final_and_executory

    # ---- HARD GATES (bypass allowed for MED-ATT-2025) ----
    if pending_summons and not allow_med_att:
        messages.warning(
            request,
            "Please mark the latest summons attendance (ATTENDED / NO SHOW) before adding a new form."
        )
        return redirect("lupon_mem:case_detail", case_id=case_id)

    if notice_outstanding and not allow_med_att:
        messages.warning(
            request,
            "There is a scheduled mediation/conciliation hearing. Please record the outcome (HELD → Settled / Not Settled) first."
        )
        return redirect("lupon_mem:case_detail", case_id=case_id)

    # ---- Decide allowed codes (KP-7..KP-25) ----
    allowed_codes: list[str] = []
    gate_msg = None

    is_settled_text = ('SETTLED' in (settlement_status_name or ''))
    latest_is_noshow = (latest_att_status == 'NO SHOW')

    if allow_med_att:
        allowed_codes = ['MED-ATT-2025']
        gate_msg = "You are adding Mediation/Pangkat Attendance for the scheduled hearing."
    else:
        if not _has('KP-7'):
            allowed_codes = ['KP-7']
            gate_msg = "Start the case: file KP-7 (Complaint)."
        else:
            if not _has('KP-9'):
                allowed_codes = ['KP-8', 'KP-9']
                gate_msg = "Issue KP-9 (Summons). You may also schedule PB Mediation (KP-8)."
            else:
                if latest_is_noshow:
                    if latest_att_party in ('COMPLAINANT','BOTH'):
                        allowed_codes.append('KP-18')
                    if latest_att_party in ('RESPONDENT','BOTH'):
                        allowed_codes.append('KP-19')
                    allowed_codes.append('KP-9')
                    if repeated_ns_compl:
                        allowed_codes.extend(['KP-21','KP-20B'])
                    if repeated_ns_resp:
                        allowed_codes.extend(['KP-22','KP-20B'])
                    gate_msg = "Latest summons marked NO SHOW — issue the proper failure form(s) and/or a new summons."
                else:
                    # Normal running track
                    allowed_codes.extend(['KP-8','KP-9','KP-10','KP-11','KP-12','MED-ATT-2025','KP-13'])
                    allowed_codes.append('KP-16')

                    if has_kp16 and within_repudiation_window:
                        allowed_codes.append('KP-17')
                    if has_kp16 and kp17_exists:
                        allowed_codes.append('KP-20')  # CFA (repudiation)

                    if (hearings_held >= 1) and (not is_settled_text) and (not notice_outstanding):
                        allowed_codes.append('KP-20A')  # CFA (no settlement)

                    if can_kp23:
                        allowed_codes.append('KP-23')
                        has_kp23 = _has('KP-23')
                        has_kp24 = _has('KP-24')
                        if has_kp23:
                            allowed_codes.append('KP-24')
                        if has_kp24:
                            allowed_codes.append('KP-25')

                    gate_msg = (
                        "Proceed with Mediation/Pangkat flow. Use KP-16 when settled; "
                        "KP-17 (within 10 days) if repudiated; KP-20A (no settlement); "
                        "KP-20B (repeated non-appearance); KP-20 (repudiation). "
                        "Use KP-23→24→25 for execution when a settlement/award is final and not complied with."
                    )

    # ---- order + dedupe ----
    wanted_order = [
        'KP-7','KP-8','KP-9','KP-10','KP-11','KP-12','KP-13',
        'MED-ATT-2025','KP-16','KP-17',
        'KP-18','KP-19',
        'KP-20','KP-20A','KP-20B',
        'KP-21','KP-22',
        'KP-23','KP-24','KP-25'
    ]
    allowed_set = {c.upper() for c in allowed_codes}
    allowed_codes = [c for c in wanted_order if c in allowed_set]

    # ---- fetch display names for allowed codes ----
    forms: list[tuple[str, str]] = []
    if allowed_codes:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(form_code) AS code, form_name
                FROM kp_form
                WHERE UPPER(form_code) = ANY(%s)
                ORDER BY array_position(%s::text[], UPPER(form_code))
            """, [allowed_codes, allowed_codes])
            forms = [(code, name) for code, name in cur.fetchall()]

    # ---- badges for template ----
    badge_flags = {
        "summons_count": summons_count,
        "no_show_complainant": latest_att_status == 'NO SHOW' and (latest_att_party in ('COMPLAINANT','BOTH')),
        "no_show_respondent":  latest_att_status == 'NO SHOW' and (latest_att_party in ('RESPONDENT','BOTH')),
        "need_new_summons": True,
        "repeated_ns_complainant": repeated_ns_compl,
        "repeated_ns_respondent":  repeated_ns_resp,
        "has_kp16": has_kp16,
        "within_repudiation_window": within_repudiation_window,
        "kp17_exists": kp17_exists,
        "final_and_executory": final_and_executory,
    }

    print(f"[add_form_choose_static] case_id={case_id} allow_med_att={allow_med_att} requested_code={requested_code} "
          f"pending_summons={pending_summons} latest_notice_outstanding={notice_outstanding} "
          f"allowed_codes={allowed_codes} badge_flags={badge_flags}")

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



def _case_has_kp16(case_id: int) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
              AND UPPER(f.form_code) = 'KP-16'
              AND UPPER(COALESCE(s.status, 'SUBMITTED')) IN ('SUBMITTED','APPROVED')
            ORDER BY s.submitted_at DESC
            LIMIT 1
        """, [case_id])
        return cur.fetchone() is not None


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_hearing_schedule(request, case_id: int):
    """
    Per-hearing page (Mediation/Conciliation).

    KEY POINTS:
    - If user selects SETTLED, require KP-16 (Amicable Settlement) to exist.
    - Count Med-ATT within the time window of the currently picked hearing.
    - Re-enable 'Add Mediation Attendance' for subsequent hearings.
    - Expose has_kp16 to the template (for the JS guard + [DEBUG] pill).
    """
    sid = _toi(request.GET.get("sid"))

    # 1) All KP-8/KP-12 hearing notices for this case, ascending by time
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
            "has_kp16": _case_has_kp16(case_id),
            "kp16_just_created": (request.GET.get("kp16") == "1"),
        })

    # 2) Decide which hearing to show (by sid or latest)
    idx = None
    if sid:
        for i, (sub_id, _, _, _) in enumerate(all_hearings):
            if sub_id == sid:
                idx = i
                break
    if idx is None:
        idx = len(all_hearings) - 1

    picked_submission_id, form_id, form_code, submitted_at = all_hearings[idx]
    hearing_source = 'KP-8' if form_code == 'KP-8' else 'KP-12'
    next_submitted_at = None
    if idx + 1 < len(all_hearings):
        next_submitted_at = all_hearings[idx + 1][3]

    # 3) Pull hearing date/time from the notice
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

    # 4) Parties
    with connection.cursor() as cur:
        cur.execute("""SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) 
                         FROM complainant_case cc JOIN person p ON p.person_id=cc.person_id
                        WHERE cc.blotter_case_id=%s ORDER BY 1""", [case_id])
        complainants = [r[0] for r in cur.fetchall()]
        cur.execute("""SELECT TRIM(COALESCE(p.first_name,'')||' '||COALESCE(p.last_name,'')) 
                         FROM respondent_case rc JOIN person p ON p.person_id=rc.person_id
                        WHERE rc.blotter_case_id=%s ORDER BY 1""", [case_id])
        respondents = [r[0] for r in cur.fetchall()]

    # 5) Held status within this hearing window
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
        held_at = (cur.fetchone() or [None])[0]

    hearing_held = bool(held_at)
    held_at_fmt = None
    if held_at:
        try:
            held_at_fmt = timezone.localtime(held_at).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            held_at_fmt = getattr(held_at, "strftime", lambda *_: None)("%b %d, %Y %I:%M %p")

    # 6) Per-hearing Med-ATT count within this window
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

    mediation_photos = _list_mediation_photos(case_id, picked_submission_id)
    has_attendance = med_attendance_count > 0 or _has_mediation_attendance(case_id)

    def _ordinal(n: int) -> str:
        s = {1:"st",2:"nd",3:"rd"}.get(0 if n%100 in (11,12,13) else n%10, "th")
        return f"{n}{s}"

    hearing_index = idx + 1
    hearing_label = f"{_ordinal(hearing_index)} Hearing"
    med_attendance_ord_label = (
        f"{_ordinal(med_attendance_count)} Mediation Attendance successfully attached"
        if med_attendance_count >= 1 else None
    )

    dev_mode = bool(getattr(settings, "DEBUG", False) or request.GET.get("dev") == "1")
    has_kp16 = _case_has_kp16(case_id)
    kp16_just_created = (request.GET.get("kp16") == "1")

    return render(request, "lupon_mem/case_hearing_schedule.html", {
        "case_id": case_id,
        "hearing_source": hearing_source,
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

        # Flags for JS guard + debug UI
        "has_kp16": has_kp16,
        "kp16_just_created": kp16_just_created,
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
# ---------- Server-side finalize: blocks SETTLED without KP-16 ----------
@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def mediation_complete(request, case_id: int):
    # Raw parse
    settlement      = (request.POST.get("settlement") or "").upper().strip()
    remarks         = (request.POST.get("remarks") or "").strip() or None
    raw_sid         = request.POST.get("submission_id")
    submission_id   = int(raw_sid) if raw_sid and raw_sid.isdigit() else None
    compl_attended  = bool(request.POST.get("compl_attended"))
    resp_attended   = bool(request.POST.get("resp_attended"))
    att_slot_only   = bool(request.POST.get("att_slot_only"))   # ← NEW: consume slot as no-show
    staff_id        = (request.session.get("auth") or {}).get("staff_id")

    # 1) Attendance requirement rules
    #    - SETTLED → require attendance
    #    - PENDING → allow zero attendance; if att_slot_only=1 and no attendance yet, consume 1st slot as "no-show"
    has_att = _has_med_attendance(case_id)

    if settlement == "SETTLED" and not has_att:
        messages.error(request, "Please add Mediation Attendance first before marking the mediation as held (SETTLED).")
        if submission_id:
            return redirect(f"{reverse('lupon_mem:case_hearing_schedule', args=[case_id])}?sid={submission_id}")
        return redirect('lupon_mem:case_hearing_schedule', case_id)

    # 2) If SETTLED, require KP-16 already on file; otherwise bounce them to create it
    if settlement == "SETTLED" and not _case_has_kp16(case_id):
        messages.info(request, "Please complete the Amicable Settlement (KP-16) before finalizing as SETTLED.")
        kp16_url = f"{reverse('lupon_mem:open_kp16_from_hearing', args=[case_id])}"
        if submission_id:
            kp16_url += f"?sid={submission_id}"
        return redirect(kp16_url)

    # 3) Ensure we’re marking the correct KP-8 (or pick latest KP-8 if none provided)
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

    # 4) rank of this schedule among all hearings (for remarks)
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

    # 5) resolve progress_type_id
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

    # 6) If PENDING and no attendance yet but att_slot_only=1, consume the 1st slot as a "no-show"
    #    We do this BEFORE inserting the HELD tracking, so any downstream readers already see the increment.
    if settlement != "SETTLED" and not has_att and att_slot_only:
        try:
            _maybe_upsert_hearing_attendance(
                case_id=case_id,
                source_code="KP-8",
                notice_sid=submission_id,
                compl_attended=False,
                resp_attended=False,
                settlement="PENDING",
                remarks=(remarks or "NO-SHOW") + " (slot consumed: no-show)",
            )
            has_att = True  # for any later logic; next real attendance will be #2
        except Exception:
            # Don't block the flow; still proceed to mark HELD, but inform user we didn't mark no-show
            messages.warning(request, "Proceeding without recording a no-show attendance slot (could not insert).")

    # 7) insert HELD tracking
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

    # 8) persist attendance flags from form (normal path)
    #    - If they left both unchecked, that's fine for PENDING; for SETTLED we already gated above.
    _maybe_upsert_hearing_attendance(
        case_id=case_id,
        source_code="KP-8",
        notice_sid=submission_id,
        compl_attended=compl_attended,
        resp_attended=resp_attended,
        settlement=settlement or "PENDING",
        remarks=remarks,
    )

    # 9) If SETTLED and KP-16 exists, optionally flip case to SETTLED
    if settlement == "SETTLED" and _case_has_kp16(case_id):
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Marked settled from KP-8 (KP-16 on file)', staff_id])
            messages.success(request, "Mediation marked HELD and case set to SETTLED.")
        except Exception:
            messages.success(request, "Mediation marked HELD. (Could not update case settlement automatically.)")
    else:
        messages.success(request, "Mediation marked HELD.")

    # back to same hearing
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
