# lupon_mem/services/summary.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from django.db import connection, transaction
from django.urls import reverse
from django.conf import settings
from django.core.exceptions import ValidationError
from common.supabase_client import supabase
from lupon_mem.services.form_renderer import render_final_pdf

def _latest_submission_for_codes(case_id: int, codes: list[str]):
    codes_up = [c.upper() for c in codes]
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id, UPPER(f.form_code) AS code, s.submitted_at
            FROM blotter_kp_submission s JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = ANY(%s)
              AND UPPER(s.status) = 'SUBMITTED'
            ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
            LIMIT 1
        """, [case_id, codes_up])
        return cur.fetchone()

# paste your existing `_autogen_settled_summary` body here UNCHANGED

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

