# lupon_mem/views.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
from notifications.service import notify_user
from common.send_sms import send_sms
from datetime import datetime
import os
import uuid
from dependency_injector.wiring import inject, Provide

from typing import Dict
from datetime import date as _date
from django.db import connection

from lupon_mem.services.forms.kp8 import KP8Handler  # reuse its normalization
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler
# add near the top with your other imports
from lupon_mem.services.timeline import get_case_timeline

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

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from common.supabase_client import supabase

from src.app.bootstrap.app_containers import AppContainer

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

from django.contrib import messages
from django.db import connection
from django.http import HttpRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from lupon_mem.services.all_helpers import *
from lupon_mem.services.all_helpers import _hearing_gate

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

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

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
    
    # Determine settlement type (MEDIATED vs CONCILIATED)
    from lupon_mem.views_reports import _get_settlement_type
    settlement_type = _get_settlement_type(case_id)
    put("settlement_type", settlement_type)  # Will be 'MEDIATED' or 'CONCILIATED'

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
            
            # Log the creation of the settlement summary
            blotter_log_event(
                action="CREATE",
                table_affected="blotter_kp_submission",
                record_affected_id=med_sid,
                details={"form_code": med_code, "case_id": case_id, "auto_generated": True},
                performer_staff_id=None  # System generated
            )

            # insert answers (only for codes that exist on the form)
            for code, val in values_by_code.items():
                field_id = med_fields[code]
                cur.execute("""
                    INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (submission_id, field_id)
                    DO UPDATE SET value_json=EXCLUDED.value_json
                """, [med_sid, field_id, _json.dumps(val)])

            # propagate 'processed_by' meta and printable fields from the KP-16 submission (if available)
            try:
                # 1) Who processed KP-16?
                cur.execute(
                    "SELECT processed_by_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [kp16_submission_id]
                )
                row_proc = cur.fetchone()
                kp16_proc_id = int(row_proc[0]) if row_proc and row_proc[0] is not None else None

                if kp16_proc_id:
                    # 2) Set MEDx processed_by_id (trigger fills processed_at/name/position)
                    cur.execute(
                        "UPDATE blotter_kp_submission SET processed_by_id=%s WHERE submission_id=%s",
                        [kp16_proc_id, med_sid]
                    )

                    # 3) Read cached values from MEDx submission
                    cur.execute(
                        """
                        SELECT processed_at, COALESCE(processed_by_name,''), COALESCE(processed_by_position,'')
                          FROM blotter_kp_submission
                         WHERE submission_id=%s
                        """,
                        [med_sid]
                    )
                    proc_at, proc_name, proc_pos = cur.fetchone() if cur.rowcount else (None, '', '')

                    # 4) Upsert printable fields if present on the form
                    cur.execute(
                        "SELECT field_code, field_id FROM kp_field WHERE field_code IN %s",
                        [("processed_by_staff_id", "processed_by_staff_name", "processed_by_staff_position", "processed_on_date", "processed_on_time")]
                    )
                    code_to_id = {fc: fid for fc, fid in cur.fetchall()}

                    def _iso(d):
                        try:
                            return d.date().isoformat()
                        except Exception:
                            return None

                    def _hm(t):
                        try:
                            return t.strftime('%H:%M')
                        except Exception:
                            return None

                    values_map = {
                        'processed_by_staff_id': str(kp16_proc_id),
                        'processed_by_staff_name': proc_name,
                        'processed_by_staff_position': proc_pos,
                        'processed_on_date': _iso(proc_at),
                        'processed_on_time': _hm(proc_at),
                    }
                    for code, val in values_map.items():
                        fid = code_to_id.get(code)
                        if not fid:
                            continue
                        cur.execute(
                            """
                            INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (submission_id, field_id)
                            DO UPDATE SET value_json = EXCLUDED.value_json
                            """,
                            [med_sid, int(fid), _json.dumps(val)]
                        )
            except Exception:
                # Non-fatal; continue with submission
                pass

            # mark submitted
            cur.execute("UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s",
                        [med_sid])
            
            # Log the submission
            blotter_log_event(
                action="UPDATE",
                table_affected="blotter_kp_submission",
                record_affected_id=med_sid,
                details={"form_code": med_code, "case_id": case_id, "auto_submitted": True},
                performer_staff_id=None,  # System generated
                field_changed="status",
                old_value="DRAFT",
                new_value="SUBMITTED"
            )

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
        
        # Log the KP-16 draft creation
        blotter_log_event(
            action="CREATE",
            table_affected="blotter_kp_submission",
            record_affected_id=sid,
            details={"form_code": "KP-16", "case_id": case_id, "status": "DRAFT"},
            performer_staff_id=None  # System generated
        )

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
        
        # Log the form submission
        blotter_log_event(
            action="CREATE",
            table_affected="blotter_kp_submission",
            record_affected_id=sid,
            details={"form_code": form_code, "case_id": case_id, "prefilled": True},
            performer_staff_id=None,  # System generated
            field_changed="status",
            new_value="SUBMITTED"
        )

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




# --- case detail ---
# lupon_mem/views.py  (replace your case_detail with this version)


# --- choose form (DB-backed; cached) ---


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

    user_role = _auth_role_name(request)
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
            'page_path': f'{user_role} / Form Builder',
            'page_title': f'Form Builder - {form_code}',
        },
    )




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
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

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
    announcements = []

    try:
        payload = lupon_mem_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json") 
    except Exception as exc:
        print("Error fetching lupon mem dashboard KPIs:", exc)

    # Get filter options for modal
    with connection.cursor() as cur:
        cur.execute("SELECT complaint_title_id, complaint_title_name FROM complaint_title ORDER BY complaint_title_name")
        complaint_titles = cur.fetchall()
        cur.execute("SELECT case_nature_id, case_name FROM case_nature ORDER BY case_name")
        case_natures = cur.fetchall()
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)

    return render(
        request,
        "lupon_mem/dashboard.html",
        {
            'page_path' : f'{user_role} / Dashboard',
            'page_title' : 'Dashboard',
            'kpis': kpis,
            'dashboard_json': dashboard_json,
            'today': datetime.now().strftime("%B %d, %Y"),
            'announcements': announcements,
            'complaint_titles': complaint_titles,
            'case_natures': case_natures,
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


from django.db import DatabaseError

def _toi(x):
    try:
        return int(x) if x not in (None, "", "0") else None
    except Exception:
        return None


# --- Case timeline (read-only) ---
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_timeline(request: HttpRequest, case_id: int):
    user_role = _auth_role_name(request)
    data = get_case_timeline(case_id)
    if not data.get("header"):
        return HttpResponseBadRequest("Case not found.")
    data.update({
        'page_path': f'{user_role} / Case Timeline',
        'page_title': 'Case Timeline',
    })
    return render(request, "lupon_mem/case_timeline.html", data)


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
    gate = hearing_gate(case_id)
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
    # COMMENTED OUT FOR NOW - DISPLAY ALL FORMS
    # if pending_summons and not allow_med_att:
    #     messages.warning(
    #         request,
    #         "Please mark the latest summons attendance (ATTENDED / NO SHOW) before adding a new form."
    #     )
    #     return redirect("lupon_mem:case_detail", case_id=case_id)

    # if notice_outstanding and not allow_med_att:
    #     messages.warning(
    #         request,
    #         "There is a scheduled mediation/conciliation hearing. Please record the outcome (HELD → Settled / Not Settled) first."
    #     )
    #     return redirect("lupon_mem:case_detail", case_id=case_id)

    # ---- DISPLAY ALL FORMS (guards commented out) ----
    from django.core.paginator import Paginator
    
    # Get all forms from KP-7 to KP-25 plus MED-ATT-2025
    wanted_order = [
        'KP-7','KP-8','KP-9','KP-10','KP-11','KP-12','KP-13',
        'MED-ATT-2025','KP-16','KP-17',
        'KP-18','KP-19',
        'KP-20','KP-20A','KP-20B',
        'KP-21','KP-22',
        'KP-23','KP-24','KP-25'
    ]
    
    # ---- return only the three specific forms ----
    all_forms = [
        ('KP-10', 'NOTICE FOR CONSTITUTION OF PANGKAT'),
        ('KP-11', 'NOTICE TO CHOSEN PANGKAT MEMBER'),
        ('KP-13', 'SUBPOENA LETTER')
    ]
    
    # ---- pagination ----
    paginator = Paginator(all_forms, 10)  # 10 forms per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    gate_msg = "All forms are displayed (guards temporarily disabled)"

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
          f"total_forms={len(all_forms)} badge_flags={badge_flags}")

    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/add_form_choose_static.html", {
        "case_id": case_id,
        "forms": page_obj.object_list,
        "page_obj": page_obj,
        "gate_msg": gate_msg,
        "badge_flags": badge_flags,
        'page_path': f'{user_role} / Add Form',
        'page_title': 'Add Form',
    })



@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    """
    Display case details with forms and timeline.
    """
    with connection.cursor() as cur:
        # Get case basic info
        cur.execute("""
            SELECT bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                   bc.date_filed, bc.time_filed, bc.incident_desc,
                   COALESCE(ct.complaint_title_name, '') AS complaint_title,
                   COALESCE(ss.settlement_status_name, 'PENDING') AS settlement_status,
                   COALESCE(cs.case_state_name, 'OPEN') AS case_state
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_row = cur.fetchone()
        if not case_row:
            return HttpResponseNotFound("Case not found")
        
        case = case_row
        
        # Get forms for this case
        cur.execute("""
            SELECT s.submission_id, UPPER(f.form_code) AS form_code, f.form_name,
                   UPPER(s.status) AS status, s.processed_by_name, s.submitted_at, s.processed_at,
                   s.processed_by_position
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
            ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
        """, [case_id])
        forms = cur.fetchall()
        
        # Get settlement statuses for modal
        cur.execute("SELECT settlement_status_id, settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
        settlement_statuses = cur.fetchall()
        
        # Get case states for modal
        cur.execute("SELECT case_state_id, case_state_name FROM case_state ORDER BY case_state_name")
        case_states = cur.fetchall()
    
    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/case_detail.html", {
        "case_id": case_id,
        "case": case,
        "forms": forms,
        "settlement_statuses": settlement_statuses,
        "case_states": case_states,
        "case_state_name": case[8] if len(case) > 8 else "OPEN",
        'page_path': f'{user_role} / Case Details',
        'page_title': f'Case #{case[1]}' if case else 'Case Details',
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def incident_heatmap(request: HttpRequest):
    """
    Display comprehensive barangay incident heatmap with advanced analytics and filtering.
    """
    # Get filter parameters
    time_filter = request.GET.get('time_filter', '1_year')
    case_type_filter = request.GET.get('case_type', 'all')
    settlement_filter = request.GET.get('settlement', 'all')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # Build time filter condition (reports)
    time_conditions = {
        '1_month': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '1 month'",
        '3_months': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '3 months'",
        '6_months': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '6 months'",
        '1_year': "AND br.date_time_reported >= CURRENT_DATE - INTERVAL '1 year'",
        'all': "",
        'custom': ""
    }
    
    # Handle custom date range
    if time_filter == 'custom' and start_date and end_date:
        time_condition = f"AND br.date_time_reported::date BETWEEN '{start_date}' AND '{end_date}'"
        case_time_condition = f"AND bc.date_filed::date BETWEEN '{start_date}' AND '{end_date}'"
    else:
        time_condition = time_conditions.get(time_filter, time_conditions['1_year'])
        # Build time filter condition (cases)
        case_time_conditions = {
            '1_month': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 month'",
            '3_months': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '3 months'",
            '6_months': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '6 months'",
            '1_year': "AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 year'",
            'all': "",
            'custom': ""
        }
        case_time_condition = case_time_conditions.get(time_filter, case_time_conditions['1_year'])

    # Build case type filter (parameterized)
    case_type_condition = ""
    case_type_params = []
    if case_type_filter != 'all':
        case_type_condition = "AND ct.complaint_title_name = %s"
        case_type_params.append(case_type_filter)

    # Build settlement filter
    settlement_condition = ""
    if settlement_filter == 'settled':
        settlement_condition = "AND (ss.settlement_status_id IN (2, 15, 16) OR UPPER(ss.settlement_status_name) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION'))"
    elif settlement_filter == 'pending':
        settlement_condition = "AND (ss.settlement_status_name IS NULL OR UPPER(ss.settlement_status_name) = 'PENDING')"
    elif settlement_filter == 'not_settled':
        settlement_condition = "AND UPPER(ss.settlement_status_name) = 'NOT SETTLED'"

    with connection.cursor() as cur:
        # ---------- 1) Incident rows ----------
        sql_incidents = f"""
            WITH incident_data AS (
                -- Blotter Reports (not yet converted to cases)
                SELECT 
                    'BR-' || br.blotter_report_id as incident_id,
                    COALESCE(br.incident_subject, 'Unnamed Incident') as incident_name,
                    COALESCE(br.incident_desc, 'No description') as incident_desc,
                    br.date_time_reported::date as date_filed,
                    br.date_time_reported::time as time_filed,
                    a.latitude,
                    a.longitude,
                    COALESCE(a.street, 'Unknown Street') as street,
                    COALESCE(a.barangay, 'Unknown Barangay') as barangay,
                    COALESCE(ps.purok_sitio_name, 'Unknown Purok') as purok,
                    'Blotter Report' as incident_type,
                    'Pending Review' as case_status,
                    'Not Applicable' as settlement_status,
                    COALESCE(pst.payment_status_name, 'Unpaid') as payment_status,
                    'Low' as severity_level,
                    br.date_time_reported as created_at,
                    '' as case_nature
                FROM blotter_report br
                LEFT JOIN addresss a ON a.address_id = br.incident_address_id
                LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                LEFT JOIN payment_status pst ON pst.payment_status_id = br.payment_status_id
                WHERE a.latitude IS NOT NULL 
                  AND a.longitude IS NOT NULL
                  {time_condition}
                  
                UNION ALL
                
                -- Blotter Cases (converted from reports or direct cases) - DEFAULT TO BARANGAY CASES ONLY
                SELECT 
                    'BC-' || bc.blotter_case_id as incident_id,
                    COALESCE(bc.blotter_case_name, 'Unnamed Case') as incident_name,
                    COALESCE(bc.incident_desc, 'No description') as incident_desc,
                    bc.date_filed::date as date_filed,
                    bc.time_filed as time_filed,
                    a.latitude,
                    a.longitude,
                    COALESCE(a.street, 'Unknown Street') as street,
                    COALESCE(a.barangay, 'Unknown Barangay') as barangay,
                    COALESCE(ps.purok_sitio_name, 'Unknown Purok') as purok,
                    COALESCE(ct.complaint_title_name, 'General Complaint') as incident_type,
                    COALESCE(cs.case_state_name, 'Open') as case_status,
                    COALESCE(ss.settlement_status_name, 'Pending') as settlement_status,
                    'Paid' as payment_status,
                    CASE 
                        WHEN ss.settlement_status_id IN (2, 15, 16) OR UPPER(ss.settlement_status_name) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION') THEN 'Low'
                        WHEN UPPER(cs.case_state_name) = 'CLOSED' THEN 'Medium'
                        WHEN bc.date_filed < CURRENT_DATE - INTERVAL '6 months' AND NOT (ss.settlement_status_id IN (2, 15, 16) OR UPPER(ss.settlement_status_name) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION')) THEN 'High'
                        ELSE 'Medium'
                    END as severity_level,
                    COALESCE(bc.date_filed::timestamp, CURRENT_TIMESTAMP) as created_at,
                    COALESCE(cn.case_name, '') as case_nature
                FROM blotter_case bc
                LEFT JOIN addresss a ON a.address_id = (
                    SELECT br.incident_address_id 
                    FROM blotter_report br 
                    WHERE br.blotter_report_id = bc.blotter_report_id
                    LIMIT 1
                )
                LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE a.latitude IS NOT NULL 
                  AND a.longitude IS NOT NULL
                  AND bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
                  {case_time_condition}
                  {case_type_condition}
                  {settlement_condition}
            )
            SELECT * FROM incident_data
            ORDER BY created_at DESC, incident_id
            LIMIT 1000
        """
        cur.execute(sql_incidents, case_type_params)
        incidents = cur.fetchall()
        print(f"[DEBUG] SQL query returned {len(incidents)} incidents")
        if incidents:
            print(f"[DEBUG] Sample incident: {incidents[0]}")
        else:
            print(f"[DEBUG] No incidents found. SQL: {sql_incidents[:200]}...")

        # ---------- 2) Stats by incident type ----------
        # FIX: remove EXTRACT(... from integer). Just average the integer day-difference.
        sql_stats = f"""
            WITH stats_data AS (
                SELECT 
                    COALESCE(ct.complaint_title_name, 'General Complaint') as incident_type,
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN ss.settlement_status_id IN (2, 15, 16) OR UPPER(ss.settlement_status_name) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION') THEN 1 END) as settled_count,
                    COUNT(CASE WHEN UPPER(cs.case_state_name) = 'CLOSED' THEN 1 END) as closed_count,
                    COUNT(CASE WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN 1 END) as mapped_count,
                    AVG(
                        CASE 
                            WHEN bc.date_filed IS NOT NULL AND ss.settlement_status_id IS NOT NULL
                            THEN (CURRENT_DATE::date - bc.date_filed::date)
                            ELSE NULL
                        END
                    ) AS avg_resolution_days
                FROM blotter_case bc
                LEFT JOIN addresss a ON a.address_id = (
                    SELECT br.incident_address_id 
                    FROM blotter_report br 
                    WHERE br.blotter_report_id = bc.blotter_report_id
                    LIMIT 1
                )
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
                {case_time_condition}
                GROUP BY ct.complaint_title_name
                
                UNION ALL
                
                SELECT 
                    'Blotter Report' as incident_type,
                    COUNT(*) as total_count,
                    0 as settled_count,
                    0 as closed_count,
                    COUNT(CASE WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN 1 END) as mapped_count,
                    NULL as avg_resolution_days
                FROM blotter_report br
                LEFT JOIN addresss a ON a.address_id = br.incident_address_id
                WHERE 1=1
                {time_condition}
            )
            SELECT incident_type, total_count, settled_count, closed_count, mapped_count, avg_resolution_days
            FROM stats_data
            WHERE total_count > 0
            ORDER BY total_count DESC
        """
        cur.execute(sql_stats)
        incident_stats = cur.fetchall()

        # ---------- 2b) Summary counts for headers ----------
        # Total blotter reports (apply selected time filter)
        cur.execute(f"SELECT COUNT(*) FROM blotter_report br WHERE 1=1 {time_condition}")
        blotter_reports_count = cur.fetchone()[0]

        # Total blotter cases (base window 2 years + selected time filter)
        cur.execute(f"SELECT COUNT(*) FROM blotter_case bc WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years' {case_time_condition}")
        blotter_cases_count = cur.fetchone()[0]

        # ---------- 3) Street-level stats ----------
        sql_streets = """
            SELECT 
                COALESCE(a.street, 'Unknown Street') as street_name,
                COALESCE(a.barangay, 'Unknown Barangay') as barangay_name,
                COUNT(*) as incident_count,
                COUNT(CASE WHEN ss.settlement_status_id IN (2, 15, 16) OR UPPER(ss.settlement_status_name) IN ('SETTLED', 'SETTLED THROUGH MEDIATION', 'SETTLED THROUGH CONCILIATION') THEN 1 END) as settled_count,
                COUNT(CASE WHEN bc.date_filed >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as recent_count,
                MAX(bc.date_filed) as last_incident_date
            FROM blotter_case bc
            LEFT JOIN addresss a ON a.address_id = (
                SELECT br.incident_address_id 
                FROM blotter_report br 
                WHERE br.blotter_report_id = bc.blotter_report_id
                LIMIT 1
            )
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE a.latitude IS NOT NULL 
              AND a.longitude IS NOT NULL
              AND bc.date_filed >= CURRENT_DATE - INTERVAL '1 year'
            GROUP BY a.street, a.barangay
            HAVING COUNT(*) >= 1
            ORDER BY incident_count DESC, recent_count DESC
            LIMIT 25
        """
        cur.execute(sql_streets)
        street_stats = cur.fetchall()

        # ---------- 4) Case type options ----------
        cur.execute("""
            SELECT DISTINCT ct.complaint_title_name
            FROM complaint_title ct
            JOIN blotter_case bc ON bc.complaint_title_id = ct.complaint_title_id
            WHERE bc.date_filed >= CURRENT_DATE - INTERVAL '2 years'
            ORDER BY ct.complaint_title_name
        """)
        case_types = [row[0] for row in cur.fetchall()]

    # -------- Format payloads for the template --------
    import json
    incident_data = []
    print(f"[DEBUG] Processing {len(incidents)} incidents from database")
    for incident in incidents:
        incident_item = {
            'id': incident[0],
            'name': incident[1] or 'Unnamed Incident',
            'description': incident[2] or 'No description',
            'date': incident[3].strftime('%Y-%m-%d') if incident[3] else '',
            'time': str(incident[4]) if incident[4] else '',
            'lat': float(incident[5]) if incident[5] else 0,
            'lng': float(incident[6]) if incident[6] else 0,
            'street': incident[7] or 'Unknown Street',
            'barangay': incident[8] or 'Unknown Barangay',
            'purok': incident[9] or 'Unknown Purok',
            'type': incident[10] or 'Unknown Type',
            'case_status': incident[11] or 'Unknown Status',
            'settlement_status': incident[12] or 'Pending',
            'payment_status': incident[13] or 'Unknown',
            'severity': incident[14] or 'Medium',
            'created_at': incident[15].strftime('%Y-%m-%d %H:%M') if incident[15] else '',
            'case_nature': incident[16] if len(incident) > 16 else ''
        }
        incident_data.append(incident_item)
    print(f"[DEBUG] First incident: {incident_data[0] if incident_data else 'No incidents'}")
    
    # Print what should be displayed for BELLOSILLO vs. ARRANCHADO case
    bellosillo_case = next((item for item in incident_data if 'BELLOSILLO' in item.get('name', '')), None)
    if bellosillo_case:
        print(f"[DEBUG] BELLOSILLO case data: {bellosillo_case}")
        print(f"[DEBUG] Expected display:")
        print(f"  - ID: {bellosillo_case.get('id', 'N/A')}")
        print(f"  - Name: {bellosillo_case.get('name', 'N/A')}")
        print(f"  - Type: {bellosillo_case.get('type', 'N/A')}")
        print(f"  - Case Nature: {bellosillo_case.get('case_nature', 'N/A')}")
        print(f"  - Status: {bellosillo_case.get('settlement_status', 'N/A')}")
        print(f"  - Description: {bellosillo_case.get('description', 'N/A')}")
    else:
        print(f"[DEBUG] BELLOSILLO case not found in incident_data")
    


    stats_data = []
    for stat in incident_stats:
        settlement_rate = round((stat[2] / stat[1] * 100) if stat[1] > 0 else 0, 1)
        # stat[5] is numeric (avg int days); leave None if null
        avg_days = round(stat[5]) if stat[5] is not None else None
        stats_data.append({
            'type': stat[0],
            'total_count': stat[1],
            'settled_count': stat[2],
            'closed_count': stat[3],
            'mapped_count': stat[4],
            'settlement_rate': settlement_rate,
            'avg_resolution_days': avg_days,
            'efficiency_score': min(100, max(0, 100 - (avg_days or 30) + settlement_rate)) if avg_days is not None else settlement_rate
        })

    street_data = []
    for street in street_stats:
        settlement_rate = round((street[3] / street[2] * 100) if street[2] > 0 else 0, 1)
        street_data.append({
            'street': street[0],
            'barangay': street[1],
            'incident_count': street[2],
            'settled_count': street[3],
            'recent_count': street[4],
            'settlement_rate': settlement_rate,
            'last_incident': street[5].strftime('%Y-%m-%d') if street[5] else 'N/A',
            'risk_level': 'High' if street[4] >= 3 else 'Medium' if street[4] >= 1 else 'Low'
        })

    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/incident_heatmap.html", {
        "incident_data_json": json.dumps(incident_data),
        "incident_data": incident_data,
        "incident_stats": json.dumps(stats_data),  # For JavaScript charts
        "street_stats": street_data,
        "blotter_reports_count": blotter_reports_count,
        "blotter_cases_count": blotter_cases_count,
        "case_types": case_types,
        "time_filter": time_filter,
        "case_type_filter": case_type_filter,
        "settlement_filter": settlement_filter,
        "start_date": start_date,
        "end_date": end_date,
        'page_path': f'{user_role} / Incident Heatmap',
        'page_title': 'Barangay Incident Heatmap & Analytics',
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

# ---------- CHANGED: report_list shows payment_status ----------
# helper to read role
def _user_role(request: HttpRequest) -> str:
    auth = request.session.get("auth") or {}
    return (auth.get("role_name") or auth.get("role") or "").strip()

# Roles
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}
LUPON_ROLES_LIST = ["BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"]  # pass to templates

from django.views.decorators.http import require_POST



# views.py
@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_hearing_list(request: HttpRequest, case_id: int):
    """
    Per-case KP-8/KP-12 notices with per-notice Held status.
    Uses fn_case_mediation_hearings function to get accurate hearing data.
    """
    from django.utils import timezone

    # Get case info
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_num, 
                   COALESCE(bc.blotter_case_name,'') AS case_title,
                   COALESCE(ct.complaint_title_name,'') AS case_type,
                   COALESCE(cn.case_name,'') AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_info = cur.fetchone()
        if not case_info:
            return render(request, "lupon_mem/hearing_list.html", {"items": []})
        
        case_num, case_title, case_type, case_nature = case_info

        # Use the fn_case_mediation_hearings function to get hearing data
        cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
        cols = [c[0] for c in cur.description] if cur.description else []
        hearing_rows = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []

    items = []
    for hearing in hearing_rows:
        # Format held_at timestamp
        held_at_fmt = None
        held_at = hearing.get('held_at')
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
            "source": hearing.get('source', ''),
            "submission_id": hearing.get('notice_sid'),
            "hearing_date": hearing.get('hearing_date'),
            "hearing_time": hearing.get('hearing_time'),
            "details": None,  # Not provided by fn_case_mediation_hearings
            "hearing_held": bool(hearing.get('hearing_held')),
            "held_at": held_at,
            "held_at_fmt": held_at_fmt,
        })

    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/hearing_list.html", {
        "items": items,
        "dev_mode": bool(getattr(settings, "DEBUG", False) or (request.GET.get("dev") == "1")),
        'page_path': f'{user_role} / Case Hearings',
        'page_title': f'Case #{case_num} Hearings' if items and items[0].get('case_num') else 'Case Hearings',
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
    - NEW: Expose settlement_outcome + last attendance + KP-14 URL for ARBITRATION UI.
    """
    from django.utils import timezone
    from django.urls import reverse

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

            # NEW: keep template JS happy even when no hearing exists
            "settlement_outcome": "",
            "compl_attended_last": False,
            "resp_attended_last": False,
            "kp14_url": reverse("lupon_mem:form_builder_by_code", args=[case_id, "KP-14"]),
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

    # ===== NEW: Pull the computed outcome/attendance from fn_case_mediation_hearings =====
    settlement_outcome = ""
    compl_attended_last = False
    resp_attended_last = False
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
        cols = [c[0] for c in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []

    # Prefer the row that matches the currently picked notice (sid)
    chosen = None
    if rows:
        for r in rows:
            if int(r.get("notice_sid") or 0) == int(picked_submission_id or 0):
                chosen = r
                break
        if not chosen:
            chosen = rows[-1]  # fallback to latest

    if chosen:
        settlement_outcome = (chosen.get("settlement_outcome") or "").upper()
        compl_attended_last = (str(chosen.get("complainant_attended") or "").upper() == "TRUE")
        resp_attended_last  = (str(chosen.get("respondent_attended") or "").upper() == "TRUE")

    # Build KP-14 link for the UI (used when ARBITRATION)
    kp14_url = reverse("lupon_mem:form_builder_by_code", args=[case_id, "KP-14"])

    user_role = _auth_role_name(request)
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

        # ===== NEW: for arbitration/settlement UI =====
        "settlement_outcome": settlement_outcome,         # e.g. ARBITRATION / SETTLED / NOT SETTLED / BOTH_NO_SHOW...
        "compl_attended_last": compl_attended_last,       # bool for JS
        "resp_attended_last": resp_attended_last,         # bool for JS
        "kp14_url": kp14_url,                             # link to build KP-14
        'page_path': f'{user_role} / Hearing Schedule',
        'page_title': 'Hearing Schedule',
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
    Uses fn_case_mediation_hearings function for each case to get accurate hearing data.
    """
    from django.utils import timezone

    # Get all cases that have hearings
    with connection.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT bc.blotter_case_id
            FROM blotter_case bc
            JOIN blotter_kp_submission s ON s.blotter_case_id = bc.blotter_case_id
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE UPPER(f.form_code) IN ('KP-8','KP-12')
            ORDER BY bc.blotter_case_id DESC
            LIMIT 100
        """)
        case_ids = [row[0] for row in cur.fetchall()]

    items = []
    for case_id in case_ids:
        with connection.cursor() as cur:
            # Get case info
            cur.execute("""
                SELECT bc.blotter_case_num, 
                       COALESCE(bc.blotter_case_name,'') AS case_title,
                       COALESCE(ct.complaint_title_name,'') AS case_type,
                       COALESCE(cn.case_name,'') AS case_nature
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            case_info = cur.fetchone()
            if not case_info:
                continue
            
            case_num, case_title, case_type, case_nature = case_info

            # Use the fn_case_mediation_hearings function to get hearing data
            cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
            cols = [c[0] for c in cur.description] if cur.description else []
            hearing_rows = [dict(zip(cols, r)) for r in cur.fetchall()] if cols else []

            for hearing in hearing_rows:
                # Format held_at timestamp
                held_at_fmt = None
                held_at = hearing.get('held_at')
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
                    "source": hearing.get('source', ''),
                    "submission_id": hearing.get('notice_sid'),
                    "hearing_date": hearing.get('hearing_date'),
                    "hearing_time": hearing.get('hearing_time'),
                    "details": None,  # Not provided by fn_case_mediation_hearings
                    "hearing_held": bool(hearing.get('hearing_held')),
                    "held_at": held_at,
                    "held_at_fmt": held_at_fmt,
                })

    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/hearing_list.html", {
        "items": items,
        "dev_mode": bool(getattr(settings, "DEBUG", False) or (request.GET.get("dev") == "1")),
        'page_path': f'{user_role} / All Hearings',
        'page_title': 'All Hearings',
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
    print(f"[_maybe_upsert_hearing_attendance] case_id={case_id}, notice_sid={notice_sid}, settlement='{settlement}'")
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
        settlement_value = settlement or ""
        print(f"[_maybe_upsert_hearing_attendance] Attempting UPDATE with settlement_value='{settlement_value}'")
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
            settlement_value, (remarks or ""),
            case_id, source_code, notice_sid
        ])
        
        print(f"[_maybe_upsert_hearing_attendance] UPDATE affected {cur.rowcount} rows")

        # if no existing row, INSERT
        if cur.rowcount == 0:
            print(f"[_maybe_upsert_hearing_attendance] Attempting INSERT with settlement_value='{settlement_value}'")
            cur.execute("""
                INSERT INTO hearing_attendance
                  (blotter_case_id, source_code, notice_submission_id,
                   held_at, complainant_attended, respondent_attended,
                   settlement_outcome, remarks)
                VALUES (%s,%s,%s, NOW(), %s,%s, NULLIF(%s,''), NULLIF(%s,''))
            """, [
                case_id, source_code, notice_sid,
                compl_attended, resp_attended,
                settlement_value, (remarks or "")
            ])
            print(f"[_maybe_upsert_hearing_attendance] INSERT completed")
        
        print(f"[_maybe_upsert_hearing_attendance] Function completed")


# =========================== VIEWS ===========================
# ---------- Server-side finalize: blocks SETTLED without KP-16 ----------
# lupon_mem/views_mediation.py  (or wherever your view lives)



# =========================== VIEWS ===========================
# ---------- Server-side finalize: blocks SETTLED without KP-16 ----------
# views_hearings.py (or wherever your mediation_complete lives)
from django.contrib import messages
from django.db import connection, transaction
from django.urls import reverse

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
    att_slot_only   = bool(request.POST.get("att_slot_only"))   # consume slot as no-show
    staff_id        = (request.session.get("auth") or {}).get("staff_id")

    print(f"[mediation_complete] START - case_id={case_id}, submission_id={submission_id}")
    print(f"[mediation_complete] compl_attended={compl_attended}, resp_attended={resp_attended}")
    print(f"[mediation_complete] settlement='{settlement}', remarks='{remarks}'")
    print(f"[mediation_complete] staff_id={staff_id}")

    # Allow direct settlement; attendance can be written later
    has_att = _has_med_attendance(case_id)
    print(f"[mediation_complete] has_att={has_att}, allowing direct settlement")

    # Ensure we are acting on a valid KP-8 (or pick latest KP-8 if none provided)
    with connection.cursor() as cur:
        if not submission_id:
            cur.execute("""
                SELECT s.submission_id
                  FROM blotter_kp_submission s
                  JOIN kp_form f ON f.form_id = s.form_id
                 WHERE s.blotter_case_id = %s
                   AND UPPER(f.form_code) = 'KP-8'
                 ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                          s.submitted_at DESC NULLS LAST,
                          s.submission_id DESC
                 LIMIT 1
            """, [case_id])
            r = cur.fetchone()
            submission_id = int(r[0]) if r else None

        cur.execute("""
            SELECT COUNT(*)
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.submission_id = %s
               AND s.blotter_case_id = %s
               AND UPPER(f.form_code) = 'KP-8'
        """, [submission_id, case_id])
        valid = (cur.fetchone() or [0])[0] == 1

    if not submission_id or not valid:
        messages.error(request, "Invalid KP-8 submission selected.")
        return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)

    # Rank (1st/2nd/…) of this schedule among all notices (KP-8/KP-12)
    with connection.cursor() as cur:
        cur.execute("""
            WITH sched AS (
              SELECT s.submission_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.blotter_case_id
                       ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
                     ) AS rn
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
              WHERE s.blotter_case_id = %s
                AND UPPER(f.form_code) IN ('KP-8','KP-12')
            )
            SELECT rn FROM sched WHERE submission_id = %s
        """, [case_id, submission_id])
        row = cur.fetchone()
        sched_rn = int(row[0]) if row else None

    # Resolve progress type: HEARING HELD
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_progress_type_id
              FROM case_progress_type
             WHERE UPPER(case_progress_type_name) = 'HEARING HELD'
             LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            messages.error(request, "Progress type 'HEARING HELD' not configured.")
            return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)
        progress_type_id = int(row[0])

    # If not SETTLED and no attendance exists but user chose to consume a slot, insert a no-show record first
    print(f"[mediation_complete] Step 4 check: settlement={settlement}, has_att={has_att}, att_slot_only={att_slot_only}")
    if settlement != "SETTLED" and not has_att and att_slot_only:
        print(f"[mediation_complete] Step 4: Creating no-show attendance slot")
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
            has_att = True
        except Exception:
            messages.warning(request, "Proceeding without recording a no-show attendance slot.")
    else:
        print(f"[mediation_complete] Step 4: Skipping no-show slot creation")

    # Insert HEARING HELD tracking (remark includes outcome)
    outcome_suffix = f", outcome={settlement}" if settlement else ""
    held_remarks = remarks or f"KP-8 held (sched #{sched_rn}); comp_att={compl_attended}, resp_att={resp_attended}{outcome_suffix}"
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, date_processed, remarks, processed_by_id)
                VALUES (%s, %s, now(), %s, %s)
                RETURNING progress_tracking_id, date_processed
            """, [case_id, progress_type_id, held_remarks, staff_id])
            
            progress_id = cur.fetchone()[0]
            
            # Get staff name and case details for logging
            staff_name = None
            case_num = None
            case_name = None
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
            
            # Build attendance message
            attendance_parts = []
            if compl_attended and resp_attended:
                attendance_parts.append("both parties attended")
            elif compl_attended:
                attendance_parts.append("complainant attended")
            elif resp_attended:
                attendance_parts.append("respondent attended")
            else:
                attendance_parts.append("no parties attended")
            
            attendance_text = ", ".join(attendance_parts)
            outcome_text = f", outcome: {settlement}" if settlement else ""
            
            message = f"{staff_name or f'Staff ID {staff_id}'} marked mediation hearing as HELD for Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'} ({attendance_text}{outcome_text})"
            
            # Log the mediation completion
            blotter_log_event(
                action="MEDIATION_HELD",
                table_affected="case_progress_tracking",
                record_affected_id=progress_id,
                details=message,
                performer_staff_id=staff_id
            )

    # Outcome branches
    print(f"[mediation_complete] settlement={settlement}, case_id={case_id}")
    if settlement == "SETTLED":
        # Set case to SETTLED and auto-create KP-16 if missing
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Marked settled from KP-8 mediation', staff_id])
            print(f"[mediation_complete] Case {case_id} set to SETTLED successfully")
            messages.success(request, "Mediation marked HELD and case set to SETTLED. Settlement agreement (KP-16) created automatically.")
        except Exception as e:
            print(f"[mediation_complete] Error setting case to SETTLED: {e}")
            messages.success(request, "Mediation marked HELD. (Could not update case settlement automatically.)")
            
            # Only create KP-16 if fn_set_case_settlement failed
            try:
                with connection.cursor() as cur:
                    cur.execute("""
                        SELECT 1
                          FROM blotter_kp_submission s
                          JOIN kp_form f ON f.form_id = s.form_id
                         WHERE s.blotter_case_id = %s
                           AND UPPER(f.form_code) = 'KP-16'
                           AND UPPER(s.status) = 'SUBMITTED'
                    """, [case_id])
                    kp16_exists = cur.fetchone() is not None

                if not kp16_exists:
                    print(f"[mediation_complete] No KP-16 exists, creating one as fallback")
                    kp16_sid = _create_and_submit_form_from_prefill(
                        case_id=case_id,
                        form_code="KP-16",
                        prefill=_prefill_minimal_for_case(case_id)
                    )
                    if kp16_sid:
                        print(f"[mediation_complete] Created fallback KP-16 submission_id={kp16_sid}")
            except Exception as fallback_e:
                print(f"[mediation_complete] Error creating fallback KP-16: {fallback_e}")

    elif settlement == "ARBITRATION":
        # Optional: mark case ARBITRATED (you already have settlement_status_id=8 seeded)
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'ARBITRATED', 'Agreed to arbitration from KP-8 mediation', staff_id])
            messages.success(request, "Mediation marked HELD and case set to ARBITRATED.")
        except Exception as e:
            print(f"[mediation_complete] Error setting case to ARBITRATED: {e}")
            messages.success(request, "Mediation marked HELD. (Could not update case settlement automatically.)")

        # Ensure KP-14 (Agreement to Arbitrate) exists - check both DRAFT and SUBMITTED
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    # Use SELECT FOR UPDATE to prevent race conditions
                    cur.execute("""
                        SELECT 1
                          FROM blotter_kp_submission s
                          JOIN kp_form f ON f.form_id = s.form_id
                         WHERE s.blotter_case_id = %s
                           AND UPPER(f.form_code) = 'KP-14'
                           AND UPPER(s.status) IN ('DRAFT', 'SUBMITTED')
                         FOR UPDATE
                    """, [case_id])
                    kp14_exists = cur.fetchone() is not None

                if not kp14_exists:
                    kp14_sid = _create_and_submit_form_from_prefill(
                        case_id=case_id,
                        form_code="KP-14",
                        prefill=_prefill_minimal_for_case(case_id)
                    )
                    if kp14_sid:
                        print(f"[mediation_complete] Created KP-14 submission_id={kp14_sid}")
                else:
                    print(f"[mediation_complete] KP-14 already exists for case {case_id}")
        except Exception as e:
            print(f"[mediation_complete] Error creating KP-14: {e}")

        # Notifications (guard import)
        try:
            from notifications.views import notify_kp14_agreement_arbitration  # adjust module if needed
            notify_kp14_agreement_arbitration(case_id=case_id)
        except Exception as e:
            print(f"[KP14] Notification skipped: {e}")

    else:
        print(f"[mediation_complete] Settlement not SETTLED/ARBITRATION, just marking held")
        messages.success(request, "Mediation marked HELD.")

    # Persist attendance + the chosen settlement string (e.g., ARBITRATION)
    print(f"[mediation_complete] Recording attendance: compl={compl_attended}, resp={resp_attended}, settlement={settlement}")
    _maybe_upsert_hearing_attendance(
        case_id=case_id,
        source_code="KP-8",
        notice_sid=submission_id,
        compl_attended=compl_attended,
        resp_attended=resp_attended,
        settlement=settlement or "PENDING",
        remarks=remarks,
    )

    print(f"[mediation_complete] END - redirecting to hearing schedule")
    return redirect(f"{reverse('lupon_mem:case_hearing_schedule', args=[case_id])}?sid={submission_id}")

@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def conciliation_complete(request, case_id: int):
    # Raw parse (mirror mediation_complete)
    settlement      = (request.POST.get("settlement") or "").upper().strip()
    remarks         = (request.POST.get("remarks") or "").strip() or None
    raw_sid         = request.POST.get("submission_id")
    submission_id   = int(raw_sid) if raw_sid and raw_sid.isdigit() else None
    compl_attended  = bool(request.POST.get("compl_attended"))
    resp_attended   = bool(request.POST.get("resp_attended"))
    att_slot_only   = bool(request.POST.get("att_slot_only"))   # consume slot as no-show
    staff_id        = (request.session.get("auth") or {}).get("staff_id")

    print(f"[conciliation_complete] START - case_id={case_id}, submission_id={submission_id}")
    print(f"[conciliation_complete] compl_attended={compl_attended}, resp_attended={resp_attended}")
    print(f"[conciliation_complete] settlement='{settlement}', remarks='{remarks}'")
    print(f"[conciliation_complete] staff_id={staff_id}")

    # Attendance presence (allow direct settlement; attendance can be written later)
    # If you have a helper like _has_conc_attendance or a generic checker, use it.
    # Otherwise, we just check via SQL against existing attendance rows for this case+KP-12
    has_att = False
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                  SELECT 1
                    FROM hearing_attendance a
                   WHERE a.blotter_case_id = %s
                     AND UPPER(COALESCE(a.source_code,'')) = 'KP-12'
                )
            """, [case_id])
            has_att = bool((cur.fetchone() or [False])[0])
    except Exception:
        # Fallback to "allow direct settlement"
        has_att = False
    print(f"[conciliation_complete] has_att={has_att}, allowing direct settlement")

    # Ensure we are acting on a valid KP-12 (or pick latest KP-12 if none provided)
    with connection.cursor() as cur:
        if not submission_id:
            cur.execute("""
                SELECT s.submission_id
                  FROM blotter_kp_submission s
                  JOIN kp_form f ON f.form_id = s.form_id
                 WHERE s.blotter_case_id = %s
                   AND UPPER(f.form_code) = 'KP-12'
                 ORDER BY (UPPER(s.status)='SUBMITTED') DESC,
                          s.submitted_at DESC NULLS LAST,
                          s.submission_id DESC
                 LIMIT 1
            """, [case_id])
            r = cur.fetchone()
            submission_id = int(r[0]) if r else None

        cur.execute("""
            SELECT COUNT(*)
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.submission_id = %s
               AND s.blotter_case_id = %s
               AND UPPER(f.form_code) = 'KP-12'
        """, [submission_id, case_id])
        valid = (cur.fetchone() or [0])[0] == 1

    if not submission_id or not valid:
        messages.error(request, "Invalid KP-12 submission selected.")
        return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)

    # Rank (1st/2nd/…) among all notices (KP-8/KP-12), same as mediation_complete
    with connection.cursor() as cur:
        cur.execute("""
            WITH sched AS (
              SELECT s.submission_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY s.blotter_case_id
                       ORDER BY s.submitted_at ASC NULLS LAST, s.submission_id ASC
                     ) AS rn
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
              WHERE s.blotter_case_id = %s
                AND UPPER(f.form_code) IN ('KP-8','KP-12')
            )
            SELECT rn FROM sched WHERE submission_id = %s
        """, [case_id, submission_id])
        row = cur.fetchone()
        sched_rn = int(row[0]) if row else None

    # Resolve progress type: HEARING HELD
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_progress_type_id
              FROM case_progress_type
             WHERE UPPER(case_progress_type_name) = 'HEARING HELD'
             LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            messages.error(request, "Progress type 'HEARING HELD' not configured.")
            return redirect("lupon_mem:case_hearing_schedule", case_id=case_id)
        progress_type_id = int(row[0])

    # If not SETTLED and no attendance exists but user chose to consume a slot, insert a no-show record first
    print(f"[conciliation_complete] Step 4 check: settlement={settlement}, has_att={has_att}, att_slot_only={att_slot_only}")
    if settlement != "SETTLED" and not has_att and att_slot_only:
        print(f"[conciliation_complete] Step 4: Creating no-show attendance slot")
        try:
            _maybe_upsert_hearing_attendance(
                case_id=case_id,
                source_code="KP-12",
                notice_sid=submission_id,
                compl_attended=False,
                resp_attended=False,
                settlement="PENDING",
                remarks=(remarks or "NO-SHOW") + " (slot consumed: no-show)",
            )
            has_att = True
        except Exception:
            messages.warning(request, "Proceeding without recording a no-show attendance slot.")
    else:
        print(f"[conciliation_complete] Step 4: Skipping no-show slot creation")

    # Insert HEARING HELD tracking (remark includes outcome)
    outcome_suffix = f", outcome={settlement}" if settlement else ""
    held_remarks = remarks or f"KP-12 held (sched #{sched_rn}); comp_att={compl_attended}, resp_att={resp_attended}{outcome_suffix}"
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, date_processed, remarks, processed_by_id)
                VALUES (%s, %s, now(), %s, %s)
                RETURNING progress_tracking_id, date_processed
            """, [case_id, progress_type_id, held_remarks, staff_id])
            
            progress_id = cur.fetchone()[0]
            
            # Get staff name and case details for logging
            staff_name = None
            case_num = None
            case_name = None
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
            
            # Build attendance message
            attendance_parts = []
            if compl_attended and resp_attended:
                attendance_parts.append("both parties attended")
            elif compl_attended:
                attendance_parts.append("complainant attended")
            elif resp_attended:
                attendance_parts.append("respondent attended")
            else:
                attendance_parts.append("no parties attended")
            
            attendance_text = ", ".join(attendance_parts)
            outcome_text = f", outcome: {settlement}" if settlement else ""
            
            message = f"{staff_name or f'Staff ID {staff_id}'} marked conciliation hearing as HELD for Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'} ({attendance_text}{outcome_text})"
            
            # Log the conciliation completion
            blotter_log_event(
                action="CONCILIATION_HELD",
                table_affected="case_progress_tracking",
                record_affected_id=progress_id,
                details=message,
                performer_staff_id=staff_id
            )

    # Outcome branches (mirror mediation_complete)
    print(f"[conciliation_complete] settlement={settlement}, case_id={case_id}")
    if settlement == "SETTLED":
        # Set case to SETTLED and auto-create KP-16 if missing
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'SETTLED', 'Marked settled from KP-12 conciliation', staff_id])
            print(f"[conciliation_complete] Case {case_id} set to SETTLED successfully")
            messages.success(request, "Conciliation marked HELD and case set to SETTLED. Settlement agreement (KP-16) created automatically.")
        except Exception as e:
            print(f"[conciliation_complete] Error setting case to SETTLED: {e}")
            messages.success(request, "Conciliation marked HELD. (Could not update case settlement automatically.)")
            
            # Only create KP-16 if fn_set_case_settlement failed
            try:
                with connection.cursor() as cur:
                    cur.execute("""
                        SELECT 1
                          FROM blotter_kp_submission s
                          JOIN kp_form f ON f.form_id = s.form_id
                         WHERE s.blotter_case_id = %s
                           AND UPPER(f.form_code) = 'KP-16'
                           AND UPPER(s.status) = 'SUBMITTED'
                    """, [case_id])
                    kp16_exists = cur.fetchone() is not None

                if not kp16_exists:
                    print(f"[conciliation_complete] No KP-16 exists, creating one as fallback")
                    kp16_sid = _create_and_submit_form_from_prefill(
                        case_id=case_id,
                        form_code="KP-16",
                        prefill=_prefill_minimal_for_case(case_id)
                    )
                    if kp16_sid:
                        print(f"[conciliation_complete] Created fallback KP-16 submission_id={kp16_sid}")
            except Exception as fallback_e:
                print(f"[conciliation_complete] Error creating fallback KP-16: {fallback_e}")

    elif settlement == "ARBITRATION":
        # Optional: mark case ARBITRATED
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT * FROM fn_set_case_settlement(%s,%s,%s,%s)",
                            [case_id, 'ARBITRATED', 'Agreed to arbitration from KP-12 conciliation', staff_id])
            messages.success(request, "Conciliation marked HELD and case set to ARBITRATED.")
        except Exception as e:
            print(f"[conciliation_complete] Error setting case to ARBITRATED: {e}")
            messages.success(request, "Conciliation marked HELD. (Could not update case settlement automatically.)")

        # Ensure KP-14 exists - check both DRAFT and SUBMITTED
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    # Use SELECT FOR UPDATE to prevent race conditions
                    cur.execute("""
                        SELECT 1
                          FROM blotter_kp_submission s
                          JOIN kp_form f ON f.form_id = s.form_id
                         WHERE s.blotter_case_id = %s
                           AND UPPER(f.form_code) = 'KP-14'
                           AND UPPER(s.status) IN ('DRAFT', 'SUBMITTED')
                         FOR UPDATE
                    """, [case_id])
                    kp14_exists = cur.fetchone() is not None

                if not kp14_exists:
                    kp14_sid = _create_and_submit_form_from_prefill(
                        case_id=case_id,
                        form_code="KP-14",
                        prefill=_prefill_minimal_for_case(case_id)
                    )
                    if kp14_sid:
                        print(f"[conciliation_complete] Created KP-14 submission_id={kp14_sid}")
                else:
                    print(f"[conciliation_complete] KP-14 already exists for case {case_id}")
        except Exception as e:
            print(f"[conciliation_complete] Error creating KP-14: {e}")

        # Notifications (guard import)
        try:
            from notifications.views import notify_kp14_agreement_arbitration  # adjust module if needed
            notify_kp14_agreement_arbitration(case_id=case_id)
        except Exception as e:
            print(f"[KP14] Notification skipped: {e}")

    else:
        print(f"[conciliation_complete] Settlement not SETTLED/ARBITRATION, just marking held")
        messages.success(request, "Conciliation marked HELD.")

    # Persist attendance + the chosen settlement string
    print(f"[conciliation_complete] Recording attendance: compl={compl_attended}, resp={resp_attended}, settlement={settlement}")
    _maybe_upsert_hearing_attendance(
        case_id=case_id,
        source_code="KP-12",
        notice_sid=submission_id,
        compl_attended=compl_attended,
        resp_attended=resp_attended,
        settlement=settlement or "PENDING",
        remarks=remarks,
    )

    print(f"[conciliation_complete] END - redirecting to hearing schedule")
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

    user_role = _auth_role_name(request)
    return render(request, "lupon_mem/summon_attendance.html", {
        "case_id": case_id,
        "case_num": case_num,
        "case_title": case_title,
        "case_caption": case_caption,
        "complaint_title": complaint_title,
        "case_nature": case_nature,
        "items": items,
        'page_path': f'{user_role} / Summon Attendance',
        'page_title': f'Summon Attendance - {case_num}',
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
            
            # Log the summon attendance update
            blotter_log_event(
                action="UPDATE",
                table_affected="kp9_attendance",
                record_affected_id=submission_id,
                details={
                    "status": status,
                    "no_show_party": party,
                    "remarks": remarks
                },
                performer_staff_id=staff_id,
                field_changed="status",
                new_value=status
            )

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
        
        # Log the MED-ATT-2025 draft creation
        blotter_log_event(
            action="CREATE",
            table_affected="blotter_kp_submission",
            record_affected_id=sid,
            details={"form_code": "MED-ATT-2025", "case_id": case_id, "status": "DRAFT"},
            performer_staff_id=None  # System generated
        )

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
