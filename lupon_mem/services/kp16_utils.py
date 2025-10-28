# lupon_mem/services/kp16_utils.py
from __future__ import annotations
from typing import Optional, Tuple, Dict
from datetime import datetime as _dt, date as _date
import logging
from django.db import connection

log = logging.getLogger(__name__)

# Keys we’ll search in KP-16 answers
_DF_KEYS   = {"date_filed","filed_date","date_of_filing","date created","date_created","date_today"}
_DAY_KEYS  = {"date_entered","this_date","date_today","date created","date_created"}
_MON_KEYS  = {"month_entered","current_month","month_today","month_created"}
_YEAR_KEYS = {"year_entered","current_year","year_today","year_created"}

# NEW: likely labels/codes that hold the KP-16 settlement statement (terms)
_TNC_KEYS = {
    # common labels
    "settlement_statement", "settlement statement",
    "terms_and_conditions", "terms and conditions",
    "agreement", "settlement terms",
    "dispositive portion", "dispositive text",
    # possible field codes
    "tnc", "terms", "agreement_text", "settlement_terms", "dispositive_portion",
}

def _try_parse_date(txt: str) -> Optional[_date]:
    if not txt:
        return None
    s = txt.strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y"):
        try:
            return _dt.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _month_to_num(m: str) -> Optional[int]:
    if not m:
        return None
    try:
        return _dt.strptime(m.strip(), "%B").month
    except Exception:
        try:
            return _dt.strptime(m.strip(), "%b").month
        except Exception:
            return None

def _latest_kp16_for_case(case_id: int) -> Optional[Tuple[int, int]]:
    """Returns (kp16_submission_id, kp16_form_id) for most recent KP-16 of the case."""
    if not case_id:
        return None
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.submission_id, s.form_id
              FROM blotter_kp_submission s
              JOIN kp_form kf ON kf.form_id = s.form_id
             WHERE s.blotter_case_id = %s
               AND (kf.form_code = 'KP-16' OR kf.form_code = 'KP16' OR kf.form_code = 'KP 16')
             ORDER BY s.submission_id DESC
             LIMIT 1
            """,
            [case_id],
        )
        row = cur.fetchone()
    return (int(row[0]), int(row[1])) if row else None

def _load_field_map(form_id: int):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT f.field_id,
                   LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                   LOWER(f.field_code) AS code
              FROM kp_form_field kff
              JOIN kp_field f ON f.field_id = kff.field_id
             WHERE kff.form_id = %s
            """,
            [form_id],
        )
        return cur.fetchall()  # [(fid, label, code), ...]

def _load_answers(submission_id: int) -> Dict[str, str]:
    """Raw read from blotter_kp_answer; JSON string stored in value_json."""
    out: Dict[str, str] = {}
    with connection.cursor() as cur:
        cur.execute(
            "SELECT field_id, value_json FROM blotter_kp_answer WHERE submission_id = %s",
            [submission_id],
        )
        for fid, vjson in cur.fetchall():
            # Keep as plain string; UI usually stored a JSON string already
            try:
                # Handle raw JSON primitives/strings
                import json as _json
                val = _json.loads(vjson)
                if isinstance(val, (dict, list)):
                    val = _json.dumps(val, ensure_ascii=False)
                elif val is None:
                    val = ""
                else:
                    val = str(val)
            except Exception:
                val = str(vjson) if vjson is not None else ""
            out[str(int(fid))] = val.strip()
    return out

def _first_match(keys, by_label, by_code) -> str:
    for k in keys:
        if k in by_label:
            return by_label[k]
        if k in by_code:
            return by_code[k]
    return ""

def _derive_kp16_date_from_answers(form_id: int, submission_id: int) -> Optional[_date]:
    """Try KP-16 date_filed, else trio."""
    rows = _load_field_map(form_id)
    answers = _load_answers(submission_id)

    # Build label/code lookups → value
    by_label: Dict[str, str] = {}
    by_code: Dict[str, str] = {}
    for fid, label, code in rows:
        v = answers.get(str(fid), "")
        if v and v.lower() != "null":
            if label: by_label[label.strip().lower()] = v
            if code:  by_code[code.strip().lower()]  = v

    # 1) Direct date_filed
    raw_df = _first_match(_DF_KEYS, by_label, by_code)
    parsed = _try_parse_date(raw_df)
    try:
        log.info("[KP16-utils] direct date_filed raw=%r parsed=%r (sub=%s)", raw_df, parsed, submission_id)
        print(f"[KP16-utils] direct date_filed raw={raw_df!r} parsed={parsed!r} (sub={submission_id})")
    except Exception:
        pass
    if parsed:
        return parsed

    # 2) Trio fallback
    day  = _first_match(_DAY_KEYS,  by_label, by_code)
    mon  = _first_match(_MON_KEYS,  by_label, by_code)
    year = _first_match(_YEAR_KEYS, by_label, by_code)
    d = None
    if day.isdigit() and year.strip().isdigit():
        mnum = _month_to_num(mon)
        if mnum:
            try:
                d = _date(int(year.strip()), mnum, int(day.strip()))
            except Exception:
                d = None
    try:
        log.info("[KP16-utils] trio date parts day=%r mon=%r year=%r parsed=%r (sub=%s)", day, mon, year, d, submission_id)
        print(f"[KP16-utils] trio day={day!r} mon={mon!r} year={year!r} parsed={d!r} (sub={submission_id})")
    except Exception:
        pass
    return d

def _case_date_filed_via_submission(submission_id: int) -> Optional[_date]:
    """Fallback: the blotter_case.date_filed linked to this submission."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT bc.date_filed
              FROM blotter_kp_submission s
              JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
             WHERE s.submission_id = %s
            """,
            [submission_id],
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None

# ----------------- PUBLIC API -----------------

def get_kp16_settlement_date_for_case(case_id: int) -> Optional[_date]:
    """
    Return the best-available settlement date from the latest KP-16 of a case.
    Priority:
      1) KP-16 'date_filed' answer
      2) KP-16 trio (date_entered + month_entered + year_entered)
      3) blotter_case.date_filed via that KP-16 submission
    """
    pair = _latest_kp16_for_case(case_id)
    if not pair:
        return None
    kp16_sub_id, kp16_form_id = pair
    d = _derive_kp16_date_from_answers(kp16_form_id, kp16_sub_id)
    if d:
        return d
    return _case_date_filed_via_submission(kp16_sub_id)

def get_kp16_settlement_date_for_submission(kp16_submission_id: int) -> Optional[_date]:
    """
    Given a *KP-16* submission id, return its settlement date with the same priority.
    """
    # fetch its form_id
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM blotter_kp_submission WHERE submission_id=%s", [kp16_submission_id])
        row = cur.fetchone()
    if not row:
        return None
    kp16_form_id = int(row[0])

    d = _derive_kp16_date_from_answers(kp16_form_id, kp16_submission_id)
    if d:
        return d
    return _case_date_filed_via_submission(kp16_submission_id)

def format_full(d: Optional[_date]) -> str:
    """Helper to format as 'Month DD, YYYY' or '' if None."""
    return d.strftime("%B %d, %Y") if isinstance(d, _date) else ""

# NEW: get settlement statement / terms text from latest KP-16 of the case
def get_kp16_settlement_text_for_case(case_id: int) -> Optional[str]:
    """
    Return the settlement statement / terms from the latest KP-16 of the case.
    Looks up by common label/code variants defined in _TNC_KEYS.
    """
    pair = _latest_kp16_for_case(case_id)
    if not pair:
        return None

    kp16_sub_id, kp16_form_id = pair
    rows = _load_field_map(kp16_form_id)
    answers = _load_answers(kp16_sub_id)

    by_label: Dict[str, str] = {}
    by_code: Dict[str, str] = {}
    for fid, label, code in rows:
        v = answers.get(str(fid), "")
        if v and v.lower() != "null":
            if label:
                by_label[label.strip().lower()] = v
            if code:
                by_code[code.strip().lower()] = v

    for key in _TNC_KEYS:
        k = key.strip().lower()
        if k in by_label:
            try:
                log.info("[KP16-utils] settlement text via label=%r (case_id=%s)", k, case_id)
            except Exception:
                pass
            return by_label[k].strip()
        if k in by_code:
            try:
                log.info("[KP16-utils] settlement text via code=%r (case_id=%s)", k, case_id)
            except Exception:
                pass
            return by_code[k].strip()

    try:
        log.info("[KP16-utils] settlement text not found in latest KP-16 (case_id=%s)", case_id)
    except Exception:
        pass
    return None
