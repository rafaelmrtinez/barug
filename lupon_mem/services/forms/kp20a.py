# lupon_mem/services/forms/kp20a.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple, List
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from .util import get_secretary_name, get_lupon_chair_name

logger = logging.getLogger(__name__)

# PDF field names for KP-20A (mirrors KP-20 layout you already use)
_KP20A_FIELDS = [
    "complainants","respondents","brgy_case_number","purpose",
    "date_filed","time_filed","respondents_2",
    "complaint_date_month","complaint_year","by","ground_of",
    "this_date","this_month","this_year","lupon_sec","chairman",
]

_KP20A_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents": {"respondents","respondent(s)","party-respondents","parties_respondents"},
    "respondents_2":{"respondents_2","respondents two","respondent_two","respondent 2","party-respondents-2"},
    "brgy_case_number":{"brgy_case_number","brgy_case_num","case number","case_no","case_num","blotter_case_num"},
    "purpose":{"purpose","for","case_purpose"},
    "date_filed":{"date_filed","filed_date","date_of_filing","date_created","date today","date_today"},
    "time_filed":{"time_filed","filed_time","time_of_filing","time_created"},
    "complaint_date_month":{"complaint_date_month","month_of_complaint","current_month","month_today"},
    "complaint_year":{"complaint_year","year_of_complaint","current_year","year_today"},
    "by":{"by","issued_by","prepared_by","repudiated_by","affiant","affiant_name"},
    "ground_of":{"ground_of","grounds","reason","basis","repudiation_grounds"},
    "this_date":{"this_date","current_date","date_today","date_entered"},
    "this_month":{"this_month","current_month","month_today","month_entered"},
    "this_year":{"this_year","current_year","year_today","year_entered"},
    "lupon_sec":{"lupon_sec","lupon secretary","secretary"},
    "chairman":{"chairman","punong barangay","barangay captain","brgy_capt"},
}

def _try_parse_date(s: str) -> Optional[_date]:
    if not s: return None
    txt = s.strip()
    fmts = ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y")
    for fmt in fmts:
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

def _case_dt_by_case_num(case_num: str) -> Tuple[Optional[_date], Optional[_time]]:
    if not case_num: return (None, None)
    with connection.cursor() as cur:
        cur.execute("SELECT date_filed, time_filed FROM blotter_case WHERE blotter_case_num=%s LIMIT 1",[case_num])
        row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)

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

class KP20AHandler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP20A_FIELDS}
            print("[KP20A] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP20A fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP20A logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)

        # label/code index for this form
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

        out: Dict[str, str] = {t: find(s) for t, s in _KP20A_SOURCES.items()}

        case_num = (out.get("brgy_case_number") or "").strip()
        d_by_num, t_by_num = _case_dt_by_case_num(case_num) if case_num else (None, None)
        d_by_sub, t_by_sub, case_num_from_sub, _case_id = _case_dt_by_submission(submission_id)
        if not case_num and case_num_from_sub:
            out["brgy_case_number"] = str(case_num_from_sub)

        d_ans = (out.get("date_filed") or "").strip()
        d_obj = _try_parse_date(d_ans) or d_by_num or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
        out["date_filed"] = _fmt_full(d_obj)

        t_ans = (out.get("time_filed") or "").strip()
        t_obj = _parse_time(t_ans) or t_by_num or t_by_sub
        out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        if not (out.get("complaint_date_month") or "").strip():
            out["complaint_date_month"] = d_obj.strftime("%B")
        if not (out.get("complaint_year") or "").strip():
            out["complaint_year"] = str(d_obj.year)

        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():  out["this_date"]  = str(today.day)
        if not (out.get("this_month") or "").strip(): out["this_month"] = today.strftime("%B")
        if not (out.get("this_year") or "").strip():  out["this_year"]  = str(today.year)

        if not (out.get("lupon_sec") or "").strip():
            out["lupon_sec"] = get_secretary_name(default=out.get("lupon_sec",""))
        if not (out.get("chairman") or "").strip():
            out["chairman"] = get_lupon_chair_name(default=out.get("chairman",""))

        for k, v in list(out.items()):
            if isinstance(v, str): out[k] = FS.sanitize_text(v)
        for k in _KP20A_FIELDS:
            out.setdefault(k, "")

        self._log(out)
        return out
