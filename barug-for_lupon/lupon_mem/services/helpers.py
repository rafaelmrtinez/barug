from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import date as _date_cls
import json as _json

from django.db import connection

# -----------------------------
# Generic small helpers
# -----------------------------
def ordinal(n: int) -> str:
    n = int(n)
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1:'st',2:'nd',3:'rd'}.get(n % 10, 'th') }"

def one_val(sql: str, params: list | tuple | None = None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        row = cur.fetchone()
        return row[0] if row else None

def row(sql: str, params: list | tuple | None = None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchone()

def rows(sql: str, params: list | tuple | None = None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()

# -----------------------------
# Submissions / forms helpers
# -----------------------------
def get_form_id(form_code: str) -> int | None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT form_id FROM kp_form WHERE UPPER(form_code)=UPPER(%s) LIMIT 1",
            [form_code],
        )
        r = cur.fetchone()
    return int(r[0]) if r else None

def submitted_codes(case_id: int) -> dict[str, bool]:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT UPPER(f.form_code) AS code,
                   BOOL_OR(UPPER(s.status)='SUBMITTED') AS is_submitted
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s
            GROUP BY 1
        """, [case_id])
        return {r[0]: bool(r[1]) for r in cur.fetchall()}

def latest_submission_for_codes(case_id: int, codes: List[str]):
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
        return cur.fetchone()  # (submission_id, code, submitted_at) or None


def create_and_submit_form_from_prefill(
    case_id: int,
    form_code: str,
    prefill: Dict[str, object] | None = None,
    staff_id: int | None = None,   # NEW: used to auto-fill "Processed By"
) -> Optional[int]:
    """
    Creates a DRAFT submission for the given case & form_code, writes answers from `prefill`,
    auto-fills internal audit fields (Processed By/Date/Time) when present in the form,
    then SUBMITS the draft. Returns submission_id or None if form not found/active.

    Auto-filled (when these field_ids exist in the form):
      - 1120: "Processed By (Staff)"  -> staff full name (or "SYSTEM")
      - 1121: "Processed On (Date)"   -> YYYY-MM-DD
      - 1122: "Processed On (Time)"   -> HH:MM
    """
    form_code_up = (form_code or "").strip().upper()

    with connection.cursor() as cur:
        # 1) Resolve form_id
        cur.execute(
            "SELECT form_id FROM kp_form WHERE UPPER(form_code)=%s AND is_active IS TRUE LIMIT 1",
            [form_code_up],
        )
        r = cur.fetchone()
        if not r:
            return None
        form_id = int(r[0])

        # 2) Create a DRAFT submission
        cur.execute("""
            INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
            VALUES (%s,%s,'DRAFT') RETURNING submission_id
        """, [case_id, form_id])
        sid = int(cur.fetchone()[0])

        # 3) Get the fields present in this form (so we only write what exists)
        cur.execute("""
            SELECT f.field_id, LOWER(f.field_code) AS code
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id=%s
        """, [form_id])
        fields = cur.fetchall()
        fields_by_id = {int(fid): (fid, code) for fid, code in fields}  # for quick membership test

        # 4) Write answers from `prefill` by matching field_code (lowercased)
        pmap = prefill or {}
        # Build a reverse map: code -> field_id(s)
        code_to_ids: Dict[str, List[int]] = {}
        for fid, code in fields:
            lc = (code or "").lower()
            if lc not in code_to_ids:
                code_to_ids[lc] = []
            code_to_ids[lc].append(int(fid))

        for code, value in pmap.items():
            lc = (code or "").lower()
            if lc not in code_to_ids:
                continue
            if value in (None, "", []):
                continue
            for target_field_id in code_to_ids[lc]:
                cur.execute("""
                    INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (submission_id, field_id)
                    DO UPDATE SET value_json=EXCLUDED.value_json
                """, [sid, int(target_field_id), _json.dumps(value)])

        # 5) Auto-fill internal audit fields if they exist in this form
        #    1120: Processed By (Staff) | 1121: Date | 1122: Time
        from datetime import datetime as _dt
        _now = _dt.now()
        _processed_date = _now.strftime("%Y-%m-%d")
        _processed_time = _now.strftime("%H:%M")

        actor_name = "SYSTEM"
        if staff_id:
            try:
                cur.execute("""
                    SELECT TRIM(
                             COALESCE(p.first_name,'') || ' ' ||
                             COALESCE(p.middle_name,'') || ' ' ||
                             COALESCE(p.last_name,'')  || ' ' ||
                             COALESCE(p.suffix,'')
                           ) AS name
                    FROM staff s
                    JOIN person p ON p.person_id = s.person_id
                    WHERE s.staff_id = %s
                """, [staff_id])
                rr = cur.fetchone()
                if rr and (rr[0] or "").strip():
                    actor_name = rr[0].strip()
            except Exception:
                # keep "SYSTEM" if anything goes wrong
                pass

        autofills = (
            (1120, actor_name),
            (1121, _processed_date),
            (1122, _processed_time),
        )
        for sys_field_id, sys_val in autofills:
            if sys_field_id in fields_by_id:
                cur.execute("""
                    INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (submission_id, field_id)
                    DO UPDATE SET value_json=EXCLUDED.value_json
                """, [sid, int(sys_field_id), _json.dumps(sys_val)])

        # 6) Submit the draft
        cur.execute(
            "UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s",
            [sid],
        )

    return sid

# -----------------------------
# Hearing/notice gate helpers
# -----------------------------
def latest_notice_submitted_at(case_id: int):
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
        r = cur.fetchone()
    return r[0] if r else None

def is_hearing_held(case_id: int, strict: bool = True) -> bool:
    latest_at = latest_notice_submitted_at(case_id)
    with connection.cursor() as cur:
        if strict and latest_at:
            cur.execute("""
                SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t
                    ON t.case_progress_type_id=cpt.case_progress_type_id
                 WHERE cpt.blotter_case_id=%s
                   AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                   AND cpt.date_processed > %s
                 LIMIT 1
            """, [case_id, latest_at])
        else:
            cur.execute("""
                SELECT 1
                  FROM case_progress_tracking cpt
                  JOIN case_progress_type t
                    ON t.case_progress_type_id=cpt.case_progress_type_id
                 WHERE cpt.blotter_case_id=%s
                   AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
                 LIMIT 1
            """, [case_id])
        return bool(cur.fetchone())

def hearings_held(case_id: int) -> int:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) 
            FROM case_progress_tracking cpt
            JOIN case_progress_type t 
              ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id = %s
              AND UPPER(t.case_progress_type_name) = 'HEARING HELD'
        """, [case_id])
        return int(cur.fetchone()[0] or 0)

def hearing_gate(case_id: int) -> dict:
    """
    Mirrors the shape your views expect, driven by fn_case_mediation_hearings.
    """
    with connection.cursor() as cur:
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
        tvf = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(ss.settlement_status_name,'PENDING') AS name
            FROM blotter_case bc
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        st = cur.fetchone()
        settlement_name = (st[0] if st else None)

    IDX = {
        "hearing_no": 0, "source": 1, "notice_sid": 2, "notice_created_at": 3,
        "hearing_date": 4, "hearing_time": 5,
        "hearing_held": 6, "held_at": 7, "held_remarks": 8,
    }

    hearings_set = len(tvf)
    hearings_held_cnt = sum(1 for r in tvf if (bool(r[IDX["hearing_held"]]) or r[IDX["held_at"]] is not None))
    latest_row = tvf[-1] if tvf else None

    latest_outstanding = False
    latest_at = latest_sid = latest_code = None
    if latest_row:
        latest_at = latest_row[IDX["notice_created_at"]]
        latest_sid = int(latest_row[IDX["notice_sid"]])
        latest_code = latest_row[IDX["source"]]
        latest_outstanding = not (bool(latest_row[IDX["hearing_held"]]) or latest_row[IDX["held_at"]] is not None)

    settlement_up = (settlement_name or '').strip().upper()
    settlement_pending = settlement_up in ('PENDING','NOT SETTLED','UNSET','FOR MEDIATION','FOR CONCILIATION')

    limit_reached = hearings_held_cnt >= 3
    can_issue = (not limit_reached) and (not latest_outstanding) and settlement_pending

    reason = ""
    if limit_reached:
        reason = "Limit reached: 3 hearings already held (proceed to Arbitration/CFA)."
    elif latest_outstanding:
        reason = "There is a scheduled hearing not yet marked HELD."
    elif not settlement_pending:
        reason = f"Settlement is “{settlement_name}” (set to Pending/Not Settled to schedule another)."

    return {
        "hearings_held": int(hearings_held_cnt or 0),
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

# -----------------------------
# Prefill & display helpers
# -----------------------------
def prefill_minimal_for_case(case_id: int) -> Dict[str, str]:
    with connection.cursor() as cur:
        cur.execute("""
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
        """, [case_id])
        row = cur.fetchone() or (None, None, None, None, "", "")
        case_num, incident_desc, incident_date, incident_time, complaint_title, case_nature = row

        cur.execute("""
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
        """, [case_id])
        cmps = ", ".join([r[0] for r in cur.fetchall()])

        cur.execute("""
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
        """, [case_id])
        resps = ", ".join([r[0] for r in cur.fetchall()])

        cur.execute("""
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
        """)
        row_pb = cur.fetchone()
        punong_barangay = (row_pb[0].strip() if row_pb and row_pb[0] else "") or "LOURDES RAMIREZ"

    today = _date_cls.today()
    today_iso  = today.isoformat()
    today_mon  = today.strftime("%B")
    today_year = str(today.year)

    def _hm(t) -> str | None:
        try:
            return t.strftime("%H:%M")
        except Exception:
            return None

    purpose = f"{(complaint_title or '').strip()} - {(case_nature or '').strip()}".strip(" -")

    return {
        "complainants": cmps,
        "respondents": resps,
        "complainants_two": cmps,
        "respondents_two": resps,

        "brgy_case_num": case_num or "",
        "brgy_case_number": case_num or "",
        "case_num": case_num or "",

        "purpose": purpose,
        "incident_date": (incident_date.isoformat() if hasattr(incident_date, "isoformat") else today_iso),
        "incident_time": _hm(incident_time) or None,

        "punong_barangay": punong_barangay,
        "brgy_capt": punong_barangay,
        "brgy_captain": punong_barangay,
        "chairman": punong_barangay,

        "date_created": today_iso,
        "month_created": today_mon,
        "year_received": today_year,
        "current_date":  today_iso,
        "current_month": today_mon,
        "current_year":  today_year,

        "settlement_statement": (incident_desc or "").strip() or "Amicable settlement reached.",
        "date_filed": today_iso,
        "time_filed": _hm(incident_time) or "14:00",
        "date_entered": today_iso,
        "month_entered": today_mon,
        "year_entered": today_year,
    }

def slice_until_code(fields_with_values: List[tuple], stop_code: Optional[str]) -> List[tuple]:
    if not stop_code:
        return fields_with_values
    stop = (stop_code or "").strip().lower()
    out: List[tuple] = []
    for item in fields_with_values:
        out.append(item)
        code = (item[6] or "").strip().lower()
        if code == stop:
            break
    return out

# -----------------------------
# Media / contacts
# -----------------------------
def list_case_photos(case_id: int) -> List[Dict[str, Any]]:
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
        data = cur.fetchall()
    return [
        {"id": r[0], "file_path": r[1], "caption": r[2], "uploaded_at": r[3]}
        for r in data
    ]

def list_mediation_photos(case_id: int, submission_id: int | None):
    out = []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT file_path, mime_type, uploaded_at
            FROM case_hearing_media
            WHERE blotter_case_id = %s
              AND media_kind = 'PHOTO'
              AND (%s IS NULL OR submission_id = %s)
            ORDER BY uploaded_at DESC
        """, [case_id, submission_id, submission_id])
        for file_path, mime_type, uploaded_at in cur.fetchall():
            path = file_path or ""
            if path.startswith("http://") or path.startswith("https://"):
                display_url = path
            else:
                from django.conf import settings
                media_url = getattr(settings, "MEDIA_URL", "/media/")
                if not media_url.endswith("/"):
                    media_url += "/"
                display_url = media_url + path.lstrip("/")
            out.append({
                "file_path": path,
                "display_url": display_url,
                "mime_type": mime_type,
                "uploaded_at": uploaded_at,
            })
    return out

def get_person_mobile_number(person_id: int) -> str | None:
    try:
        with connection.cursor() as cur:
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
                r = cur.fetchone()
                if r:
                    for val in r:
                        if isinstance(val, str) and val.strip():
                            return val.strip()
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
