# lupon_mem/services/fields_util.py
from django.db import connection
from typing import List, Dict, Any

# --- helpers for picking specific fields from the returned rows ---

from typing import Any, Dict, Iterable, List, Optional
from datetime import datetime, date, time

def rows_to_text_map(rows: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """
    Convert function result rows into {field_code -> value_text}.
    """
    out: Dict[str, Optional[str]] = {}
    for r in rows:
        out[str(r.get("field_code"))] = r.get("value_text")
    return out

def rows_to_json_map(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert function result rows into {field_code -> value_json}.
    """
    out: Dict[str, Any] = {}
    for r in rows:
        out[str(r.get("field_code"))] = r.get("value_json")
    return out

def get_field_text(rows: List[Dict[str, Any]], code: str) -> Optional[str]:
    """
    Return value_text for a given field_code (or None if not present).
    """
    code = code.strip()
    for r in rows:
        if str(r.get("field_code")) == code:
            return r.get("value_text")
    return None

def get_field_json(rows: List[Dict[str, Any]], code: str) -> Any:
    """
    Return value_json for a given field_code (or None).
    """
    code = code.strip()
    for r in rows:
        if str(r.get("field_code")) == code:
            return r.get("value_json")
    return None

# --- optional typed parsers (best-effort) ---

def parse_date_safe(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def parse_time_safe(s: Optional[str]) -> Optional[time]:
    """
    Best-effort time parser (24-hr only). Kept for backward compatibility.
    """
    if not s:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None

def parse_time_flexible(s: Optional[str]) -> Optional[time]:
    """
    Flexible time parser: supports 24-hr and 12-hr (am/pm, case-insensitive).
    Examples it handles:
      - 20:05, 20:05:30
      - 8 PM, 08 PM, 8:05 pm, 08:05 PM, 8:05 p.m., 8:05pm
    """
    if not s:
        return None
    raw = s.strip()

    # Normalize common punctuations like "p.m." -> "PM"
    lowered = raw.lower().replace(".", "").replace("  ", " ").strip()

    candidates = [raw, lowered.upper()]
    # If "am"/"pm" present without space (e.g., "8:05pm"), insert a space for parsing
    for marker in ("am", "pm"):
        if marker in lowered and f" {marker}" not in lowered:
            idx = lowered.rfind(marker)
            with_space = lowered[:idx] + " " + lowered[idx:]
            candidates.append(with_space.upper())

    fmts = [
        "%H:%M:%S",
        "%H:%M",
        "%I:%M %p",
        "%I %p",
    ]
    for cand in candidates:
        for fmt in fmts:
            try:
                return datetime.strptime(cand.strip(), fmt).time()
            except ValueError:
                continue
    return None

def get_date(rows: List[Dict[str, Any]], code: str) -> Optional[date]:
    return parse_date_safe(get_field_text(rows, code))

def get_time(rows: List[Dict[str, Any]], code: str) -> Optional[time]:
    # Keep using the original limited parser for generic calls
    return parse_time_safe(get_field_text(rows, code))

def get_latest_form_fields(case_id: int, form_code: str) -> List[Dict[str, Any]]:
    """
    Simplest version.
    Runs:
        SELECT * FROM get_latest_form_submission_fields(%s, %s);
    Returns: list of dictionaries (rows).
    """
    sql = "SELECT * FROM get_latest_form_submission_fields(%s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [case_id, form_code])
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

# Optional: quick test helper
def test_kp8_case88():
    """Example: SELECT * FROM get_latest_form_submission_fields(88, 'KP-8');"""
    rows = get_latest_form_fields(88, 'KP-8')
    for row in rows:
        print(row)
    return rows

# -------------------------------
# KP-7 helpers
# -------------------------------

def get_this_case_kp7_date_filed(case_id: int) -> Optional[str]:
    """
    Returns a formatted date string for the KP-7 'date filed' composed from:
        date_created (month name) + month_created (day number) + year_received
    Example output: "December 03, 2025"
    Returns None if any of the parts are missing.
    """
    rows = get_latest_form_fields(case_id, 'KP-7')
    month = (get_field_text(rows, 'date_created') or '').strip()  # Month name
    day = (get_field_text(rows, 'month_created') or '').strip()   # Day number
    year = (get_field_text(rows, 'year_received') or '').strip()

    if not (month and day and year):
        return None

    # Normalize day: "29th" -> "29", ensure 2 digits
    if not day.isdigit():
        digits = ''.join(ch for ch in day if ch.isdigit())
        day = digits or day
    if day.isdigit():
        day = f"{int(day):02d}"

    return f"{month} {day}, {year}"

def get_this_case_kp7_time_filed(case_id: int) -> Optional[str]:
    """
    Returns the KP-7 'time filed' in 12-hour format with AM/PM (e.g., '8:17 PM').
    It searches common time field codes in priority order:
        case_time_filed, time_filed, filed_time, time_of_filing, time_created
    Returns None if not available or unparsable.
    """
    rows = get_latest_form_fields(case_id, 'KP-7')
    candidates = [
        'case_time_filed',
        'time_filed',
        'filed_time',
        'time_of_filing',
        'time_created',
    ]

    raw_time: Optional[str] = None
    for code in candidates:
        val = get_field_text(rows, code)
        if val and str(val).strip():
            raw_time = str(val).strip()
            break

    if not raw_time:
        return None

    t = parse_time_flexible(raw_time)
    if not t:
        return None

    # Format to 12-hour with AM/PM; remove leading zero on hour.
    s = t.strftime("%I:%M %p")
    if s.startswith("0"):
        s = s[1:]
    return s



# -------------------------------
# KP-16 helpers
# -------------------------------

from typing import Optional  # if not already imported at top

def get_this_case_kp16_date_filed(case_id: int) -> Optional[str]:
    """
    Returns KP-16 'date filed' as: month_entered + date_entered + year_entered
    Example: 'October 29, 2025'
    """
    rows = get_latest_form_fields(case_id, 'KP-16')
    month = (get_field_text(rows, 'month_entered') or '').strip()
    day   = (get_field_text(rows, 'date_entered') or '').strip()
    year  = (get_field_text(rows, 'year_entered') or '').strip()

    if not (month and day and year):
        return None

    # Normalize day like "29th" -> "29"
    if not day.isdigit():
        digits = ''.join(ch for ch in day if ch.isdigit())
        day = digits or day

    return f"{month} {day}, {year}"

def get_this_case_kp16_settlement_agreement(case_id: int) -> Optional[str]:
    """
    Returns the KP-16 settlement agreement text (field: settlement_statement).
    """
    rows = get_latest_form_fields(case_id, 'KP-16')
    val = (get_field_text(rows, 'settlement_statement') or '').strip()
    return val or None

def get_barangay_captain_name() -> str:
    """
    Fetches the current barangay captain name from the database.
    Returns formatted name: "FIRST M. LAST" or fallback to "Lourdes Ramirez".
    """
    sql = """
        SELECT p.first_name, p.middle_name, p.last_name, p.suffix
        FROM staff s
        JOIN person p ON p.person_id = s.person_id
        WHERE s.role_id = 3 AND s.acc_status_id = 1
        LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        if row:
            first, middle, last, suffix = row
            middle_initial = f"{middle[0]}." if middle else ""
            parts = [first, middle_initial, last]
            if suffix:
                parts.append(suffix)
            return " ".join(p for p in parts if p).strip()
    return "Lourdes Ramirez"
