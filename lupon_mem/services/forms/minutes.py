# lupon_mem/services/forms/minutes.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple, List
import json, logging, re
from datetime import datetime as _dt, date as _date, time as _time
from zoneinfo import ZoneInfo

from django.db import connection
from .. import form_shared as FS
from .util import get_secretary_name, get_captain_name  # Barangay Secretary & Chairman
from .util import get_lupon_chair_name, get_case_time_filed_from_kp7

logger = logging.getLogger(__name__)

# Exact field names expected in your Minutes PDF
_FIELDS = [
    "complainants","respondents","brgy_case_num","purpose",
    "date_filed","time_filed",
    "who","when","where","what",
    "date_signed","month_signed","year_signed","time_signed",
    "complainants_two","respondents_two",
    "brgy_sec","brgy_chairman",
]

# Accepted sources to fill each target (KP-7 style: allow label/code lookups)
_SOURCES: Dict[str, Set[str]] = {
    "complainants":   {"complainants","complainant(s)","party-complainants","complainant_name","complainants_2"},
    "respondents":    {"respondents","respondent(s)","party-respondents","respondent_name","respondents_2"},
    "brgy_case_num":  {"barangay case no.","barangay_case_no","brgy_case_num","brgy_case_number","case_num"},
    "purpose":        {"for","for_section","purpose","complaint_title","case_nature"},
    "date_filed":     {"date_filed","date_received","date_created","date_signed"},
    "time_filed":     {"time_filed","time_failed","time_signed","time_received"},
    "what":           {"what","complaint","complaint_details","solutions_seeked"},
    # "who","when","where" are computed below
    # "date_signed","month_signed","year_signed","time_signed" computed (current)
    # "complainants_two","respondents_two" duplicated from collected values
    # "brgy_sec","brgy_chairman" pulled from util
}

_PH_TZ = ZoneInfo("Asia/Manila")

def _now_ph() -> _dt:
    return _dt.now(_PH_TZ)

def _fmt_12h_time(t: Optional[_time]) -> str:
    if not t:
        return ""
    s = t.strftime("%I:%M %p").lstrip("0")
    return s.lower()

def _fmt_12h_dt(dt: _dt) -> str:
    # for current time → "h:mm am/pm"
    h = dt.strftime("%I").lstrip("0") or "12"
    return f"{h}{dt.strftime(':%M %p').lower()}"

def _normalize_person_side(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

# ---------- DB helpers (mirrors KP-16 approach) ----------
def _load_case_datetime_by_case_num(case_num: str) -> Tuple[Optional[_date], Optional[_time]]:
    if not case_num:
        return None, None
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT bc.date_filed, bc.time_filed
              FROM blotter_case bc
             WHERE bc.blotter_case_num = %s
             LIMIT 1
            """,
            [case_num],
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return row[0], row[1]

def _load_case_datetime_from_submission(submission_id: int) -> Tuple[Optional[_date], Optional[_time], Optional[str]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT bc.date_filed, bc.time_filed, bc.blotter_case_num
              FROM blotter_kp_submission s
              JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
             WHERE s.submission_id = %s
            """,
            [submission_id],
        )
        row = cur.fetchone()
    if not row:
        return None, None, None
    return row[0], row[1], row[2]

class MinutesHandler:
    """
    Minutes of Hearing filler:
      - WHO:  "<Complainants> vs <Respondents>"
      - WHEN: current date as "Month DD, YYYY"
      - WHERE: "Barangay Senor Santo Nino Barangay Hall"
      - date_signed/month_signed/year_signed/time_signed: current PH date/time (12-hour w/ am/pm)
      - Barangay Secretary/Chairman pulled from util helpers
      - time_filed: same source as KP-16 (blotter_case.time_filed) via case no. or submission; fallback to answer, then current time
    """
    @staticmethod
    def _fmt_time_12h(t: Optional[_time]) -> str:
        if not t:
            return ""
        s = t.strftime("%I:%M %p")  # 01..12
        s = s.lstrip("0")
        return s.lower()            # e.g., "7:06 pm"

    def _log(self, out: Dict[str, str]) -> None:
        try:
            print(
                "[MINUTES] fill map (ordered):\n",
                json.dumps({k: out.get(k, "") for k in _FIELDS}, ensure_ascii=False, indent=2),
            )
        except Exception:
            pass

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

        # Fetch labels & codes to allow lookup by either (like KP-7)
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT f.field_id,
                       LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                       LOWER(f.field_code)
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id = kff.field_id
                WHERE kff.form_id = %s
                """,
                [form_id],
            )
            rows = cur.fetchall()

        by_label: Dict[str, str] = {}
        by_code: Dict[str, str] = {}

        for fid, label, code in rows:
            val = answers_by_id.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = val
                if code:
                    by_code[code.strip().lower()] = val

        def _find_any(keys: Set[str]) -> str:
            for k in keys:
                k = (k or "").strip().lower()
                if k in by_label:
                    return FS.normalize(by_label[k])
                if k in by_code:
                    return FS.normalize(by_code[k])
            return ""

        # Start with simple mapped values
        out: Dict[str, str] = {}
        for target, sources in _SOURCES.items():
            out[target] = _find_any(sources)

        # Duplicate convenience
        if not out.get("complainants_two") and out.get("complainants"):
            out["complainants_two"] = out["complainants"]
        if not out.get("respondents_two") and out.get("respondents"):
            out["respondents_two"] = out["respondents"]

        # ----------------- Computed WHO/WHEN/WHERE -----------------
        # WHO: "<Complainants> vs <Respondents>"
        c_side = _normalize_person_side(out.get("complainants", ""))
        r_side = _normalize_person_side(out.get("respondents", ""))
        if c_side or r_side:
            out["who"] = f"{c_side} vs {r_side}".strip(" vs ")
        else:
            out["who"] = ""

        # WHEN: Use from form if provided, otherwise use current PH date
        when_str = _find_any({"when", "hearing_date", "date_of_hearing"})
        if when_str:
            out["when"] = when_str
        else:
            today = _now_ph().date()
            out["when"] = f"{today.strftime('%B')} {today.day:02d}, {today.year}"

        # WHERE: fixed text
        out["where"] = "Barangay Senor Santo Nino Barangay Hall"

        # ----------------- Date/time for signatures: use date_signed and time_signed from form if provided --------
        # Check if date_signed was provided in the form
        date_signed_str = _find_any({"date_signed", "date signed", "signature_date"})
        
        if date_signed_str:
            # Try to parse the date_signed field
            try:
                # Try ISO format first
                signed_date = _dt.strptime(date_signed_str.strip(), "%Y-%m-%d").date()
            except:
                try:
                    # Try other common formats
                    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"):
                        try:
                            signed_date = _dt.strptime(date_signed_str.strip(), fmt).date()
                            break
                        except:
                            continue
                    else:
                        signed_date = _now_ph().date()
                except:
                    signed_date = _now_ph().date()
        else:
            signed_date = _now_ph().date()
        
        # Check if time_signed was provided in the form
        time_signed_str = _find_any({"time_signed", "time signed", "signature_time"})
        
        if time_signed_str:
            # Try to parse the time_signed field
            try:
                # Try various time formats
                for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
                    try:
                        signed_time = _dt.strptime(time_signed_str.strip(), fmt).time()
                        break
                    except:
                        continue
                else:
                    signed_time = _now_ph().time()
            except:
                signed_time = _now_ph().time()
        else:
            signed_time = _now_ph().time()
        
        out["date_signed"] = f"{signed_date.day:02d}"       # day like "24"
        out["month_signed"] = signed_date.strftime("%B")     # month like "October"
        out["year_signed"]  = str(signed_date.year)         # year like "2025"
        out["time_signed"]  = _fmt_12h_time(signed_time)    # "6:49 pm"

        # ----------------- DATE & TIME FILED: from blotter_case ----
        # 1) Prefer case number lookup
        case_num_ans = (out.get("brgy_case_num") or "").strip()
        case_date_by_num, case_time_by_num = _load_case_datetime_by_case_num(case_num_ans) if case_num_ans else (None, None)

        # 2) Fallback via submission join (and also fill case num if missing)
        case_date_by_sub, case_time_by_sub, case_num_from_sub = _load_case_datetime_from_submission(submission_id)
        if not case_num_ans and case_num_from_sub:
            out["brgy_case_num"] = str(case_num_from_sub or "")

        # 3) Use date_filed and time_filed from blotter_case
        date_obj = case_date_by_sub if isinstance(case_date_by_sub, _date) else None
        time_obj = case_time_by_sub if isinstance(case_time_by_sub, _time) else None
        
        if not time_obj:
            time_obj = case_time_by_num if case_time_by_num else None
        
        out["date_filed"] = date_obj.strftime("%Y-%m-%d") if date_obj else ""
        out["time_filed"] = self._fmt_time_12h(time_obj)

        # ----------------- Officials -------------------------------
        out["brgy_sec"] = get_secretary_name(default=out.get("brgy_sec", "") or "")
        out["brgy_chairman"] = get_captain_name(default=out.get("brgy_chairman", "") or "")

        # ----------------- Final sanitize & ensure all fields ------
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)

        for k in _FIELDS:
            out.setdefault(k, "")

        self._log(out)
        return out
