# lupon_mem/services/forms/kp7_utils.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date
import json
import logging
from zoneinfo import ZoneInfo

from django.db import connection
from lupon_mem.services import form_shared as FS

logger = logging.getLogger(__name__)
PH_TZ = ZoneInfo("Asia/Manila")

FORM_CODE = "KP-7"  # Complaint
ROLE_PUNONG_BARANGAY = "BARANGAY CAPTAIN"

# ---------- Public API --------------------------------------------------------

def build_kp7_context(
    case_id: int,
    answers: Dict[str, Any] | None,
    staff_id: int | None = None,
) -> Dict[str, Any]:
    """
    Prepare a normalized KP-7 context dict ready for the KP-7 handler/PDF.
    - Pulls case header + parties
    - Normalizes complainants/respondents text blocks
    - Derives date fields (created/received)
    - Picks current Punong Barangay name from officials
    - Merges with free-text 'complaint_details', 'solutions_seeked', and 'purpose'
    """
    answers = answers or {}

    header = _fetch_case_header(case_id)
    parties = _fetch_case_parties(case_id)

    complainants_txt = _names_block(parties.get("complainants", []))
    respondents_txt  = _names_block(parties.get("respondents", []))

    dt_now = datetime.now(PH_TZ)
    d_today = dt_now.date()

    # Prefer provided dates, else use "today"
    date_created  = _as_date(answers.get("date_created")) or d_today
    date_received = _as_date(answers.get("date_received")) or d_today

    # Get PB name (graceful fallback: header.get punong barangay if present)
    pb_name = _resolve_punong_barangay_name() or header.get("punong_barangay") or ""

    ctx = {
        # Parties
        "complainants": complainants_txt,
        "respondents": respondents_txt,

        # Case info
        "case_num": header.get("case_num") or header.get("case_number") or "",
        "purpose": (answers.get("purpose") or header.get("purpose") or "").strip() or "COMPLAINT",

        # Body fields
        "complaint_details": (answers.get("complaint_details") or "").strip(),
        "solutions_seeked": (answers.get("solutions_seeked") or "").strip(),

        # Dates (split for your template fields)
        "date_created": date_created.strftime("%d"),
        "month_created": date_created.strftime("%B").upper(),
        "year_received": date_created.strftime("%Y"),

        "complainants_2": complainants_txt,  # many legacy KP-7 templates duplicate this

        "date_received": date_received.strftime("%d"),
        "month_received": date_received.strftime("%B").upper(),
        "year_received_2": date_received.strftime("%Y"),

        "punong_barangay": pb_name,
    }

    # Keep raw (sometimes handlers need them)
    ctx["_raw"] = {
        "header": header,
        "parties": parties,
        "now": dt_now.isoformat(),
        "answers": answers,
        "staff_id": staff_id,
    }
    return ctx

def persist_kp7_submission(
    case_id: int,
    staff_id: int | None,
    ctx: Dict[str, Any],
    extra_meta: Dict[str, Any] | None = None,
) -> int:
    """
    1) Insert blotter_kp_submission for KP-7
    2) Upsert per-field answers via FS.upsert_answers_by_keys (label/code variants)
    3) Optionally link parties and record hearing (not applicable to KP-7)
    """
    meta = {"form_code": FORM_CODE, "case_id": case_id}
    if extra_meta:
        meta.update(extra_meta)

    # -- Insert submission (generic)
    form_id = _resolve_form_id(FORM_CODE)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blotter_kp_submission(form_id, blotter_case_id, submitted_by_id, submitted_at, meta)
            VALUES (%s, %s, %s, NOW(), %s)
            RETURNING submission_id
            """,
            [form_id, case_id, staff_id, json.dumps(meta)],
        )
        sid = cur.fetchone()[0]

    # -- Upsert answers per field using your FS helper
    _upsert_ctx_to_answers_kp7(form_id, sid, ctx)

    # -- Optional: link parties if table exists
    _link_submission_parties_safe(sid, case_id)

    logger.info("KP-7 persisted: submission_id=%s case_id=%s", sid, case_id)
    return sid


def _resolve_form_id(form_code: str) -> int:
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)=UPPER(%s) LIMIT 1", [form_code])
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Unknown KP form_code '{form_code}'. Seed kp_form first.")
    return int(row[0])


def _upsert_ctx_to_answers_kp7(form_id: int, submission_id: int, ctx: Dict[str, Any]) -> None:
    """
    Map context -> fields by label/code variants.
    Adjust/add variants to match your KP-7 template's labels or field_codes.
    """
    kv = []

    # Parties
    kv.append( ({"complainant(s)", "complainants", "complainants_2", "complainant name"}, ctx.get("complainants", "")) )
    kv.append( ({"respondent(s)", "respondents", "respondent name"}, ctx.get("respondents", "")) )

    # Case number (many templates vary)
    case_no_val = ctx.get("case_num", "")
    kv.append( ({"barangay case no.", "brgy_case_num", "brgy_case_number", "case_num"}, case_no_val) )

    # Purpose / For:
    kv.append( ({"for", "purpose"}, ctx.get("purpose", "")) )

    # Complaint details body:
    kv.append( ({"complaint", "complaint details", "details"}, ctx.get("complaint_details", "")) )

    # Solutions seeked:
    kv.append( ({"solutions seeked", "solutions sought", "relief prayed for"}, ctx.get("solutions_seeked", "")) )

    # Dates (many KP-7 use day, month, year widgets)
    kv.append( ({"date signed", "date created", "date entered", "date filed", "date"}, ctx.get("date_created", "")) )
    kv.append( ({"month created", "month filed", "month"}, ctx.get("month_created", "")) )
    kv.append( ({"year created", "year filed", "year", "year received", "year received 2"}, ctx.get("year_received", "")) )

    # Date received (if your template has explicit receive fields)
    kv.append( ({"date received", "date_received"}, ctx.get("date_received", "")) )
    kv.append( ({"month received", "month_received"}, ctx.get("month_received", "")) )
    kv.append( ({"year received", "year_received_2"}, ctx.get("year_received_2", "")) )

    # PB signature/name
    kv.append( ({"punong barangay", "pb_name", "captain_name"}, ctx.get("punong_barangay", "")) )

    # Push to DB
    try:
        FS.upsert_answers_by_keys(form_id, submission_id, kv)
    except Exception as e:
        logger.warning("KP-7 upsert via FS.upsert_answers_by_keys failed: %s", e)

# ---------- Internals: Data fetch --------------------------------------------

def _fetch_case_header(case_id: int) -> Dict[str, Any]:
    """
    Try FS, then fallback to canonical snapshot table: blotter_case (+ joins).
    """
    # Prefer shared helper if present
    if hasattr(FS, "fetch_case_header"):
        try:
            return FS.fetch_case_header(case_id) or {}
        except Exception as e:
            logger.warning("FS.fetch_case_header failed; fallback to SQL: %s", e)

    sql = """
    SELECT
      bc.blotter_case_id        AS case_id,
      bc.case_number            AS case_num,
      ct.complaint_title_name   AS complaint_title,
      bc.created_at,
      bc.updated_at,
      pb.person_full_name       AS punong_barangay
    FROM blotter_case bc
    LEFT JOIN complaint_title ct
      ON ct.complaint_title_id = bc.complaint_title_id
    LEFT JOIN (
      -- Current Punong Barangay, if you keep an officials view/helper.
      SELECT s.staff_id, p.person_id, p.full_name AS person_full_name
      FROM staff s
      JOIN person p ON p.person_id = s.person_id
      JOIN rolee r  ON r.role_id = s.role_id
      WHERE UPPER(r.role_name) = 'BARANGAY CAPTAIN'
      AND COALESCE(s.acc_status_id, 1) IS NOT NULL
      LIMIT 1
    ) pb ON TRUE
    WHERE bc.blotter_case_id = %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [case_id])
        row = _one_dict(cur)
    return row or {}


def _fetch_case_parties(case_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Pull complainants/respondents as lists of {person_id, name}.
    Tries FS first, then raw joins on complainant_case/respondent_case.
    """
    if hasattr(FS, "fetch_case_people"):
        try:
            d = FS.fetch_case_people(case_id) or {}
            if d:
                return d
        except Exception as e:
            logger.warning("FS.fetch_case_people failed; fallback to SQL: %s", e)

    sql_complainants = """
      SELECT c.person_id, COALESCE(p.full_name, p.first_name || ' ' || p.last_name) AS name
      FROM complainant_case c
      JOIN person p ON p.person_id = c.person_id
      WHERE c.blotter_case_id = %s
      ORDER BY p.last_name, p.first_name
    """
    sql_respondents = """
      SELECT r.person_id, COALESCE(p.full_name, p.first_name || ' ' || p.last_name) AS name
      FROM respondent_case r
      JOIN person p ON p.person_id = r.person_id
      WHERE r.blotter_case_id = %s
      ORDER BY p.last_name, p.first_name
    """
    with connection.cursor() as cur:
        cur.execute(sql_complainants, [case_id])
        complainants = [{"person_id": pid, "name": name} for pid, name in cur.fetchall()]
        cur.execute(sql_respondents, [case_id])
        respondents = [{"person_id": pid, "name": name} for pid, name in cur.fetchall()]
    return {"complainants": complainants, "respondents": respondents}


# ---------- Internals: Submission IO -----------------------------------------

def _raw_insert_submission(
    form_code: str,
    case_id: int,
    staff_id: int | None,
    answers: Dict[str, Any],
    meta: Dict[str, Any],
) -> int:
    """
    Generic raw insert into blotter_kp_submission + answers.
    Assumes you have kp_form table with form_code unique.
    """
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM kp_form WHERE UPPER(form_code)=UPPER(%s) LIMIT 1", [form_code])
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Unknown KP form_code '{form_code}'. Seed kp_form first.")
        form_id = row[0]

        cur.execute(
            """
            INSERT INTO blotter_kp_submission(form_id, blotter_case_id, submitted_by_id, submitted_at, meta)
            VALUES (%s, %s, %s, NOW(), %s)
            RETURNING submission_id
            """,
            [form_id, case_id, staff_id, json.dumps(meta)],
        )
        sid = cur.fetchone()[0]

        # save answers
        cur.execute(
            """
            INSERT INTO blotter_kp_answer(submission_id, answers_json, created_at)
            VALUES (%s, %s, NOW())
            """,
            [sid, json.dumps(answers)],
        )
    logger.info("Inserted KP submission (raw) form=%s sid=%s case=%s", form_code, sid, case_id)
    return sid


def _link_submission_parties_safe(submission_id: int, case_id: int) -> None:
    """
    If you keep a link table for who received the notice/form, attach parties.
    No-op if table is absent.
    """
    try:
        parties = _fetch_case_parties(case_id)
        rows: List[Tuple[int, str]] = []
        for p in parties.get("complainants", []):
            rows.append((p["person_id"], "COMPLAINANT"))
        for p in parties.get("respondents", []):
            rows.append((p["person_id"], "RESPONDENT"))
        if not rows:
            return
        with connection.cursor() as cur:
            cur.execute("""
            SELECT to_regclass('public.blotter_kp_submission_party')
            """)
            if cur.fetchone()[0] is None:
                return  # table not present; skip silently

            cur.executemany(
                """
                INSERT INTO blotter_kp_submission_party(submission_id, person_id, party_role)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [(submission_id, pid, role) for pid, role in rows],
            )
    except Exception as e:
        logger.warning("Linking submission parties skipped: %s", e)


# ---------- Internals: Utilities ---------------------------------------------

def _resolve_punong_barangay_name() -> Optional[str]:
    # Prefer FS helper if present
    if hasattr(FS, "get_official_by_role_name"):
        try:
            pb = FS.get_official_by_role_name(ROLE_PUNONG_BARANGAY)
            if pb and isinstance(pb, dict):
                return pb.get("full_name") or pb.get("name")
        except Exception as e:
            logger.warning("FS.get_official_by_role_name failed: %s", e)
    return None


def _names_block(items: List[Dict[str, Any]]) -> str:
    names = [i.get("name") for i in items if (i and i.get("name"))]
    return "; ".join(names).upper() if names else ""


def _as_date(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except Exception:
            pass
    return None


def _one_dict(cur) -> Optional[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    row = cur.fetchone()
    if not row:
        return None
    return {cols[i]: row[i] for i in range(len(cols))}


def _strip_private(ctx: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(ctx)
    d.pop("_raw", None)
    return d
