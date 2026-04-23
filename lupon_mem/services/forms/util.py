from __future__ import annotations
from typing import Optional, Dict
from django.db import connection
from .. import form_shared as FS

# Known role IDs (from your seeds)
ROLE_CAPTAIN = 3
ROLE_SECRETARY = 4
ROLE_LUPON_PRESIDENT = 7

def _name_from_person(first: str, middle: str, last: str, suffix: str) -> str:
    parts = [first or "", middle or "", last or "", suffix or ""]
    return " ".join([p for p in parts if p]).replace("  ", " ").strip()

def _get_official_by_role_id(role_id: int) -> Optional[Dict[str, str]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   p.first_name, p.middle_name, p.last_name, p.suffix,
                   COALESCE(p.mobile_num, '') AS mobile_num
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            WHERE s.role_id = %s
            ORDER BY s.staff_id DESC
            LIMIT 1
            """,
            [role_id],
        )
        row = cur.fetchone()
    if not row:
        return None
    _, first, middle, last, suffix, mobile = row
    name = FS.sanitize_text(_name_from_person(first, middle, last, suffix))
    return {"name": name, "mobile": FS.sanitize_text(mobile or "")}

def _get_official_by_role_name(role_name: str) -> Optional[Dict[str, str]]:
    """
    Looks up the latest staff by rolee.role_name (ILIKE).
    Example names: 'BARANGAY LUPON PRESIDENT', 'BARANGAY LUPON MEMBER', etc.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.staff_id,
                   p.first_name, p.middle_name, p.last_name, p.suffix,
                   COALESCE(p.mobile_num, '') AS mobile_num
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee r   ON r.role_id = s.role_id
            WHERE r.role_name ILIKE %s
            ORDER BY s.staff_id DESC
            LIMIT 1
            """,
            [role_name],
        )
        row = cur.fetchone()
    if not row:
        return None
    _, first, middle, last, suffix, mobile = row
    name = FS.sanitize_text(_name_from_person(first, middle, last, suffix))
    return {"name": name, "mobile": FS.sanitize_text(mobile or "")}

def get_captain_name(default: str = "") -> str:
    rec = _get_official_by_role_id(ROLE_CAPTAIN)
    return rec["name"] if rec and rec.get("name") else default

def get_secretary_name(default: str = "") -> str:
    rec = _get_official_by_role_id(ROLE_SECRETARY)
    return rec["name"] if rec and rec.get("name") else default

def get_lupon_chair_name(default: str = "") -> str:
    """
    Pangkat Chairman == Lupon Chair/President.
    We search by role name to avoid depending on a numeric ID.
    """
    rec = _get_official_by_role_id(ROLE_LUPON_PRESIDENT)
    return rec["name"] if rec and rec.get("name") else default


def case_has_kp16(case_id: int) -> bool:
    """
    Returns True if the case has at least one KP-16 (Amicable Settlement) submission.
    We ignore voided records.
    """
    sql = """
        SELECT 1
        FROM blotter_kp_submission s
        JOIN kp_form f ON f.form_id = s.form_id
        WHERE f.form_code = 'KP-16'
          AND s.blotter_case_id = %s
          AND COALESCE(s.is_void, FALSE) = FALSE
        ORDER BY s.submitted_at DESC
        LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [case_id])
        return cur.fetchone() is not None


from datetime import time as _time
import re
from django.db import connection

def get_case_time_filed_from_kp7(submission_id: int) -> _time | None:
    """
    Returns the case_time_filed (TIME) saved in KP-7 form for the same blotter_case
    as the given submission_id.
    If not found or unparsable, returns None.
    """
    with connection.cursor() as cur:
        cur.execute("""
            SELECT a.value_json
              FROM blotter_kp_submission s
              JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
              JOIN blotter_kp_submission s7 ON s7.blotter_case_id = bc.blotter_case_id
              JOIN kp_form kf7 ON kf7.form_id = s7.form_id
              JOIN blotter_kp_answer a ON a.submission_id = s7.submission_id
              JOIN kp_field f ON f.field_id = a.field_id
             WHERE s.submission_id = %s
               AND kf7.form_code = 'KP-7'
               AND f.field_code = 'case_time_filed'
             LIMIT 1;
        """, [submission_id])
        row = cur.fetchone()

    if not row or not row[0]:
        return None

    txt = str(row[0]).strip().strip('"')
    txt = re.sub(r"\s+", " ", txt)
    try:
        from datetime import datetime as _dt
        for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
            try:
                return _dt.strptime(txt, fmt).time()
            except Exception:
                continue
    except Exception:
        pass
    return None
