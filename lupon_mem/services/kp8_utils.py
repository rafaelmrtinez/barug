# lupon_mem/services/forms/kp8_utils.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, time
import json
import logging
from zoneinfo import ZoneInfo

from django.db import connection
from lupon_mem.services import form_shared as FS

logger = logging.getLogger(__name__)
PH_TZ = ZoneInfo("Asia/Manila")

FORM_CODE = "KP-8"  # Notice of Hearing (Mediation)
DEFAULT_VENUE = "BARANGAY HALL"
ROLE_PUNONG_BARANGAY = "BARANGAY CAPTAIN"

# ---------- Public API --------------------------------------------------------

def build_kp8_context(
    case_id: int,
    answers: Dict[str, Any] | None,
    staff_id: int | None = None,
) -> Dict[str, Any]:
    """
    Prepare context for KP-8 (first hearing/mediation notice).
    - Determines hearing date/time/place (from answers if provided)
    - Computes 'hearing_no' as 1 + count(KP-8/KP-12) already issued
    - Prefills parties and PB name
    """
    answers = answers or {}
    header = _fetch_case_header(case_id)
    parties = _fetch_case_parties(case_id)

    complainants_txt = _names_block(parties.get("complainants", []))
    respondents_txt  = _names_block(parties.get("respondents", []))

    # Determine next hearing number (counts KP-8 + KP-12)
    hearing_no = _compute_next_hearing_no(case_id)

    # Parse schedule from answers or propose next working day 9:00 AM
    sched_date, sched_time = _parse_schedule(answers)
    if not sched_date:
        sched_date = _next_working_day(date.today())
    if not sched_time:
        sched_time = time(9, 0, 0)

    venue = (answers.get("venue") or answers.get("place") or DEFAULT_VENUE).upper()

    pb_name = _resolve_punong_barangay_name() or header.get("punong_barangay") or ""

    ctx = {
        # Parties
        "complainants": complainants_txt,
        "respondents": respondents_txt,

        # Case
        "case_num": header.get("case_num") or header.get("case_number") or "",
        "punong_barangay": pb_name,

        # Hearing meta
        "hearing_no": hearing_no,
        "hearing_date": sched_date.strftime("%B %d, %Y").upper(),
        "hearing_time": sched_time.strftime("%I:%M %p").lstrip("0"),
        "hearing_place": venue,

        # Optional copy/wording controls
        "purpose": (answers.get("purpose") or "MEDIATION").upper(),
        "notes": (answers.get("notes") or "").strip(),
    }

    ctx["_raw"] = {
        "header": header,
        "parties": parties,
        "answers": answers,
        "staff_id": staff_id,
        "sched_date": sched_date.isoformat() if sched_date else None,
        "sched_time": sched_time.strftime("%H:%M:%S") if sched_time else None,
    }
    return ctx


def persist_kp8_submission(
    case_id: int,
    staff_id: int | None,
    ctx: Dict[str, Any],
    extra_meta: Dict[str, Any] | None = None,
) -> int:
    """
    Insert KP-8 submission, then optionally record a derived 'hearing set' row
    (if you maintain a separate hearing schedule table).
    """
    payload = _strip_private(ctx)
    meta = {"form_code": FORM_CODE, "case_id": case_id}
    if extra_meta:
        meta.update(extra_meta)

    # Prefer FS helper
    if hasattr(FS, "create_kp_submission"):
        try:
            sid = FS.create_kp_submission(
                form_code=FORM_CODE,
                case_id=case_id,
                submitted_by_id=staff_id,
                answers=payload,
                meta=meta,
            )
            _link_submission_parties_safe(sid, case_id)
            _maybe_record_hearing_set(sid, case_id, ctx)
            logger.info("KP-8 persisted via FS.create_kp_submission sid=%s", sid)
            return sid
        except Exception as e:
            logger.warning("FS.create_kp_submission failed; fallback to raw insert: %s", e)

    # Fallback raw
    sid = _raw_insert_submission(FORM_CODE, case_id, staff_id, payload, meta)
    _link_submission_parties_safe(sid, case_id)
    _maybe_record_hearing_set(sid, case_id, ctx)
    return sid


# ---------- Internals: Data fetch --------------------------------------------

def _fetch_case_header(case_id: int) -> Dict[str, Any]:
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


# ---------- Internals: Hearing helpers ---------------------------------------

def _compute_next_hearing_no(case_id: int) -> int:
    """
    Count prior mediation/conciliation notices (KP-8 + KP-12) and return next ordinal.
    Uses either:
      - FS.count_hearing_notices(case_id), or
      - Raw count via blotter_kp_submission joined to kp_form
    """
    if hasattr(FS, "count_hearing_notices"):
        try:
            n = int(FS.count_hearing_notices(case_id) or 0)
            return n + 1
        except Exception as e:
            logger.warning("FS.count_hearing_notices failed; fallback to SQL: %s", e)

    sql = """
      SELECT COUNT(*)::int
      FROM blotter_kp_submission s
      JOIN kp_form f ON f.form_id = s.form_id
      WHERE s.blotter_case_id = %s
        AND UPPER(f.form_code) IN ('KP-8','KP-12')
    """
    with connection.cursor() as cur:
        cur.execute(sql, [case_id])
        n = cur.fetchone()[0]
    return int(n) + 1


def _parse_schedule(answers: Dict[str, Any]) -> Tuple[Optional[date], Optional[time]]:
    """
    Accepts a wide set of keys:
      - 'hearing_date' (YYYY-MM-DD or dd/mm/YYYY etc), 'hearing_time' (HH:MM)
      - or 'date' / 'time'
      - or 'schedule_date' / 'schedule_time'
    """
    dkeys = ("hearing_date", "date", "schedule_date")
    tkeys = ("hearing_time", "time", "schedule_time")

    d = None
    for k in dkeys:
        d = d or _as_date(answers.get(k))
    t = None
    for k in tkeys:
        t = t or _as_time(answers.get(k))
    return d, t


def _maybe_record_hearing_set(submission_id: int, case_id: int, ctx: Dict[str, Any]) -> None:
    """
    Optional: if you maintain a structured hearing table, record the set schedule here.
    This is a light wrapper that no-ops if the table isn't present.
    """
    try:
        with connection.cursor() as cur:
            # guard: is hearing table present?
            cur.execute("SELECT to_regclass('public.blotter_hearing')")
            if cur.fetchone()[0] is None:
                return

            # upsert-ish insert
            cur.execute(
                """
                INSERT INTO blotter_hearing (
                  blotter_case_id, submission_id, hearing_no,
                  hearing_date, hearing_time, hearing_place, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
                """,
                [
                    case_id,
                    submission_id,
                    ctx.get("hearing_no"),
                    _parse_datefmt(ctx.get("hearing_date")),
                    _parse_timefmt(ctx.get("hearing_time")),
                    (ctx.get("hearing_place") or DEFAULT_VENUE),
                ],
            )
    except Exception as e:
        logger.warning("Record hearing_set skipped: %s", e)


# ---------- Internals: Submission IO -----------------------------------------

def _raw_insert_submission(
    form_code: str,
    case_id: int,
    staff_id: int | None,
    answers: Dict[str, Any],
    meta: Dict[str, Any],
) -> int:
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
            cur.execute("SELECT to_regclass('public.blotter_kp_submission_party')")
            if cur.fetchone()[0] is None:
                return
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


def _as_time(v: Any) -> Optional[time]:
    if not v:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, str):
        v = v.strip().upper()
        # Accept "9:00", "09:00", "9:00 AM", "09:00 PM"
        for fmt in ("%H:%M", "%I:%M %p"):
            try:
                return datetime.strptime(v, fmt).time()
            except Exception:
                pass
    return None


def _next_working_day(today: date) -> date:
    # Simple: if Sat(5)/Sun(6), push to Monday
    wd = today.weekday()
    if wd == 5:
        return today.replace(day=today.day + 2)
    if wd == 6:
        return today.replace(day=today.day + 1)
    return today


def _parse_datefmt(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _parse_timefmt(s: Optional[str]) -> Optional[time]:
    if not s:
        return None
    for fmt in ("%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
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
