# lupon_mem/services/forms/kp23.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple, List
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from ..kp16_utils import get_kp16_settlement_date_for_case, format_full  # ← KP-16 date helper
from ..form_shared import upsert_answers_by_keys  # ← generic DB upsert by label/code

logger = logging.getLogger(__name__)

# PDF fields from kp_form_no_23.pdf
_KP23_FIELDS = [
    "complainants","respondents","case_num","purpose",
    "date_filed","purpose_2","time_filed","on_date",
    "this_date","this_month","this_year",
    "complainants_two","respondents_two",
]

_KP23_SOURCES: Dict[str, Set[str]] = {
    "complainants":{"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents":{"respondents","respondent(s)","party-respondents","parties_respondents"},
    "case_num":{"case_num","case_no","brgy_case_num","brgy_case_number","blotter_case_num"},
    "purpose":{"purpose","for","case_purpose"},
    "date_filed":{"date_filed","filed_date","date_of_filing","date_created"},
    "purpose_2":{"purpose_2","purpose two"},
    "time_filed":{"time_filed","filed_time","time_of_filing","time_created"},
    "on_date":{"on_date","order_dated","ordered_date"},
    "this_date":{"this_date","current_date","date_today","date_entered"},
    "this_month":{"this_month","current_month","month_today","month_entered"},
    "this_year":{"this_year","current_year","year_today","year_entered"},
    "complainants_two":{"complainants_two","complainants two"},
    "respondents_two":{"respondents_two","respondents two"},
}

# ---------- helpers ----------

def _try_parse_date(s: str) -> Optional[_date]:
    if not s: return None
    txt = s.strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y"):
        try: return _dt.strptime(txt, fmt).date()
        except Exception: pass
    return None

def _month_name_to_number(m: str) -> Optional[int]:
    if not m: return None
    try: return _dt.strptime(m.strip(), "%B").month
    except Exception:
        try: return _dt.strptime(m.strip(), "%b").month
        except Exception: return None

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

# ---------- DB lookups ----------

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

# ---------- main ----------

class KP23Handler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP23_FIELDS}
            print("[KP23] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP23 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP23 logging failed: %s", e)

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

        out: Dict[str, str] = {t: find(s) for t, s in _KP23_SOURCES.items()}

        # Case context from current submission
        d_by_sub, t_by_sub, case_num, case_id = _case_dt_by_submission(submission_id)
        if not (out.get("case_num") or "").strip() and case_num:
            out["case_num"] = str(case_num)

        # KP-23 own date/time
        d_ans = (out.get("date_filed") or "").strip()
        d_obj = _try_parse_date(d_ans) or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
        out["date_filed"] = _fmt_full(d_obj)

        t_ans = (out.get("time_filed") or "").strip()
        t_obj = _parse_time(t_ans) or t_by_sub
        out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        # ---- “On _____” = KP-16 settlement date (via kp16_utils) ----
        if not (out.get("on_date") or "").strip():
            d16 = get_kp16_settlement_date_for_case(case_id or 0)
            if d16:
                out["on_date"] = format_full(d16)
                try:
                    logger.info("[KP23] Using KP-16 settlement date for on_date: %s (case_id=%s)", out["on_date"], case_id)
                    print(f"[KP23] on_date <= KP-16 settlement date: {out['on_date']} (case_id={case_id})")
                except Exception:
                    pass

        # fallback: mirror KP-23 date_filed
        if not (out.get("on_date") or "").strip():
            out["on_date"] = _fmt_full(d_obj)

        # Today trio
        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():  out["this_date"]  = str(today.day)
        if not (out.get("this_month") or "").strip(): out["this_month"] = today.strftime("%B")
        if not (out.get("this_year") or "").strip():  out["this_year"]  = str(today.year)

        # sanitize + ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str): out[k] = FS.sanitize_text(v)
        for k in _KP23_FIELDS:
            out.setdefault(k, "")

        self._log(out)
        return out

    # ---------- NEW: Persist computed values (called by submit_form universal hook) ----------
    def persist_computed(self, *, form_id: int, submission_id: int, case_id: int, out_map: dict) -> None:
        """
        Persist KP-23 server-computed answers to blotter_kp_answer.
        We now save: on_date, this_date, this_month, this_year,
        complainants_two, respondents_two, and purpose_2 (if present).
        """
        try:
            out = out_map or {}

            # --- on_date (prefer KP-16 date) ---
            on_date_val = (out.get("on_date") or "").strip()
            if not on_date_val:
                d16 = get_kp16_settlement_date_for_case(case_id or 0)
                if d16:
                    on_date_val = format_full(d16)

            # --- today trio (use exactly what was used in PDF; fallback PH today) ---
            ph_today = _dt.now(ZoneInfo("Asia/Manila")).date()
            day_val   = (out.get("this_date")  or str(ph_today.day)).strip()
            month_val = (out.get("this_month") or ph_today.strftime("%B")).strip()
            year_val  = (out.get("this_year")  or str(ph_today.year)).strip()

            # --- duplicates & optional secondary purpose ---
            compl2 = (out.get("complainants_two") or out.get("complainants") or "").strip()
            resp2  = (out.get("respondents_two")  or out.get("respondents")  or "").strip()
            purpose2 = (out.get("purpose_2") or "").strip()

            # Upsert by label/code variants that might exist on the form
            keysets_to_values = [
                ({"on_date","order_dated","ordered_date"}, on_date_val),
                ({"this_date","current_date","date_today","date_entered"}, day_val),
                ({"this_month","current_month","month_today","month_entered"}, month_val),
                ({"this_year","current_year","year_today","year_entered"}, year_val),
                ({"complainants_two","complainants two"}, compl2),
                ({"respondents_two","respondents two"}, resp2),
            ]

            if purpose2:
                keysets_to_values.append(({"purpose_2","purpose two"}, purpose2))

            upsert_answers_by_keys(
                form_id=form_id,
                submission_id=submission_id,
                keysets_to_values=keysets_to_values,
            )
        except Exception:
            logger.exception("KP23.persist_computed failed (sid=%s)", submission_id)
            # non-fatal