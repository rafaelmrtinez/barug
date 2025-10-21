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
