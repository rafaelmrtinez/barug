# lupon_mem/services/forms/kp25.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple, List
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
# Use KP-16 settlement date + settlement text
from ..kp16_utils import (
    get_kp16_settlement_date_for_case,
    format_full,
    get_kp16_settlement_text_for_case,  # ← NEW
)
# Use KP-7 date/time fields
from ..fields_util import (
    get_this_case_kp7_date_filed,
    get_this_case_kp7_time_filed,
)

logger = logging.getLogger(__name__)

# PDF fields from kp_form_no_25.pdf
_KP25_FIELDS = [
    "complainants","respondents","case_num","purpose",
    "date_filed","time_filed","whereas_on","TnC",
    "party_obligation","name_of_party_obliged","amount_of_settlement",
    "this_date","this_month","this_year",
    "complainants_sig","respondents_sig",
]

_KP25_SOURCES: Dict[str, Set[str]] = {
    "complainants":{"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents":{"respondents","respondent(s)","party-respondents","parties_respondents"},
    "case_num":{"case_num","case_no","brgy_case_num","brgy_case_number","blotter_case_num"},
    "purpose":{"purpose","for","case_purpose"},
    "date_filed":{"date_filed","filed_date","date_of_filing","date_created"},
    "time_filed":{"time_filed","filed_time","time_of_filing","time_created"},
    "whereas_on":{"whereas_on","order_dated","ordered_date","on_date"},
    "TnC":{"TnC","terms","terms_and_conditions","agreement","settlement_statement"},
    # as requested
    "party_obligation":{"respondents","respondent(s)","party-respondents","parties_respondents"},
    "name_of_party_obliged":{"respondents","respondent(s)","party-respondents","parties_respondents"},
    "amount_of_settlement":{"amount_of_settlement","amount","settlement_amount"},
    # current date trio (examples: 10-23-2025 → "23", "October", "2025")
    "this_date":{"this_date","current_date","date_today","date_entered"},
    "this_month":{"this_month","current_month","month_today","month_entered"},
    "this_year":{"this_year","current_year","year_today","year_entered"},
    "complainants_sig":{"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents_sig":{"respondents","respondent(s)","party-respondents","parties_respondents"},
}

def _try_parse_date(s: str) -> Optional[_date]:
    if not s: return None
    txt = s.strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y"):
        try: return _dt.strptime(txt, fmt).date()
        except Exception: pass
    return None

def _fmt_full(d: _date) -> str:
    return d.strftime("%B %d, %Y")

def _fmt12(t: Optional[_time]) -> str:
    if not t: return ""
    return t.strftime("%I:%M %p").lstrip("0").lower()

def _parse_time(s: str) -> Optional[_time]:
    if not s: return None
    txt = re.sub(r"\s+"," ", s.strip().lower())
    m = re.match(r"^(\d{1,2}):(\d{1,2})(?::\d{1,2})?\s*([ap]\.?m\.?)?$", txt)
    if m:
        hh, mm, ap = m.groups(); mm = f"{int(mm):02d}"
        if ap:
            ap = ap.replace(".","")
            try: return _dt.strptime(f"{int(hh)}:{mm} {ap}", "%I:%M %p").time()
            except Exception: pass
        else:
            try: return _dt.strptime(f"{int(hh):02d}:{mm}", "%H:%M").time()
            except Exception: pass
    for fmt in ("%H:%M","%H:%M:%S","%I:%M %p","%I:%M%p","%I %p"):
        try: return _dt.strptime(txt, fmt).time()
        except Exception: pass
    return None

# Return case_id too so we can read KP-16 data for this case
def _case_dt_by_submission(submission_id: int) -> Tuple[Optional[_date], Optional[_time], Optional[str], Optional[int]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT bc.date_filed, bc.time_filed, bc.blotter_case_num, bc.blotter_case_id
              FROM blotter_kp_submission s
              JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
             WHERE s.submission_id=%s
            """,[submission_id]
        )
        row = cur.fetchone()
    return (row[0], row[1], row[2], row[3]) if row else (None, None, None, None)

class KP25Handler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP25_FIELDS}
            print("[KP25] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP25 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP25 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)

        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT f.field_id,
                       LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                       LOWER(f.field_code) AS code
                  FROM kp_form_field kff
                  JOIN kp_field f ON f.field_id = kff.field_id
                 WHERE kff.form_id = %s
                """,[form_id]
            )
            rows = cur.fetchall()

        by_label: Dict[str, str] = {}
        by_code: Dict[str, str] = {}
        for fid, label, code in rows:
            v = answers.get(str(fid))
            if isinstance(v, str): v = FS.sanitize_text(v)
            if v not in (None, "", "null"):
                if label: by_label[label.strip().lower()] = v
                if code:  by_code[code.strip().lower()]  = v

        def find(keys: Set[str]) -> str:
            for k in keys:
                kk = k.strip().lower()
                if kk in by_label: return FS.normalize(by_label[kk])
                if kk in by_code:  return FS.normalize(by_code[kk])
            return ""

        out: Dict[str, str] = {t: find(s) for t, s in _KP25_SOURCES.items()}

        # Case context (includes case_id)
        d_by_sub, t_by_sub, case_num, case_id = _case_dt_by_submission(submission_id)
        if not (out.get("case_num") or "").strip() and case_num:
            out["case_num"] = str(case_num)

        # Own date/time - use KP-7 fields if available
        kp7_date = get_this_case_kp7_date_filed(case_id or 0)
        kp7_time = get_this_case_kp7_time_filed(case_id or 0)
        
        if kp7_date:
            out["date_filed"] = kp7_date
        else:
            d_ans = (out.get("date_filed") or "").strip()
            d_obj = _try_parse_date(d_ans) or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
            out["date_filed"] = _fmt_full(d_obj)

        if kp7_time:
            out["time_filed"] = kp7_time
        else:
            t_ans = (out.get("time_filed") or "").strip()
            t_obj = _parse_time(t_ans) or t_by_sub
            out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        # Whereas, on ______ : prefer KP-16 settlement date
        if not (out.get("whereas_on") or "").strip():
            d16 = get_kp16_settlement_date_for_case(case_id or 0)
            out["whereas_on"] = format_full(d16) if d16 else _fmt_full(d_obj)

        # Terms & Conditions: prefer KP-16 settlement statement
        if not (out.get("TnC") or "").strip():
            tnc = get_kp16_settlement_text_for_case(case_id or 0)
            if tnc:
                out["TnC"] = tnc

        # ── Current date trio (PH time), regardless of date_filed ──
        today_ph = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():
            out["this_date"] = str(today_ph.day)          # e.g., 23
        if not (out.get("this_month") or "").strip():
            out["this_month"] = today_ph.strftime("%B")   # e.g., October
        if not (out.get("this_year") or "").strip():
            out["this_year"] = str(today_ph.year)         # e.g., 2025

        # sanitize + ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str): out[k] = FS.sanitize_text(v)
        for k in _KP25_FIELDS:
            out.setdefault(k, "")

        self._log(out)
        return out
