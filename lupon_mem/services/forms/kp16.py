# lupon_mem/services/forms/kp16.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time

import json
import logging
import re

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Exact PDF field names in kp_form_no_16_ammicable_settlement.pdf
_KP16_FIELDS = [
    "complainants",
    "respondents",
    "brgy_case_num",
    "purpose",
    "date_filed",              # FULL date, e.g., "October 07, 2025"
    "time_filed",              # 12-hr, e.g., "7:06 pm"
    "settlement_statement",
    "date_entered",            # day (1..31)
    "month_entered",           # full month name
    "year_entered",            # 4-digit year
    "complainants_two",
    "respondents_two",
    "chairman",
]

# Accept both label text and field_code variants from the builder
_KP16_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants":     {"complainants", "complainant(s)", "party-complainants", "parties_complainants"},
    "respondents":      {"respondents", "respondent(s)", "party-respondents", "parties_respondents"},
    "complainants_two": {"complainants_two", "complainants 2", "complainant_two", "complainant 2",
                         "additional_complainants", "party-complainants-2"},
    "respondents_two":  {"respondents_two", "respondents 2", "respondent_two", "respondent 2",
                         "additional_respondents", "party-respondents-2"},

    # Case number
    "brgy_case_num": {
        "brgy_case_num", "brgy_case_number", "brgy case no.", "brgy case number",
        "barangay case no.", "case number", "case no.", "case_num", "blotter_case_num"
    },

    # Purpose / “For”
    "purpose": {"purpose", "for", "case_purpose"},

    # Filing date/time (from answers if provided)
    "date_filed": {"date_filed", "filed_date", "date_of_filing", "date created", "date_created", "date_today"},
    "time_filed": {"time_filed", "filed_time", "time_of_filing", "time_created"},

    # Settlement text
    "settlement_statement": {
        "settlement_statement", "amicable_settlement", "settlement_terms", "agreement_terms",
        "details_of_settlement", "narrative", "description"
    },

    # Entered date trio
    "date_entered":  {"date_entered", "current_date", "this_date", "date_today", "date_created"},
    "month_entered": {"month_entered", "current_month", "month_today", "month_created"},
    "year_entered":  {"year_entered", "current_year", "year_today", "year_created"},

    # Chairman / PB
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
}


class KP16Handler:
    """
    KP-16: AMICABLE SETTLEMENT

    Behavior:
      • Pull values from saved answers by label or field_code (robust to common variants).
      • If complainants_two/respondents_two are blank, mirror the primary lines.
      • date_filed:
           - Prefer by matching **brgy_case_num** against blotter_case.blotter_case_num.
           - If not available, fall back to submission → blotter_case join.
           - If still not available, compose from (date_entered, month_entered, year_entered) or use PH today.
           - Always format "Month DD, YYYY".
      • time_filed:
           - Same lookup preference as date (by case number first).
           - Always format as 12-hr "h:mm am/pm" (lowercase).
      • entered date trio defaults to PH today if missing.
      • Logs raw DB values and the final ordered fill map.
    """

    # ---------- parsing / formatting helpers ----------

    @staticmethod
    def _try_parse_date(s: str) -> _date | None:
        """Parse various date strings into a date object."""
        if not s:
            return None
        txt = s.strip()
        # Common numeric & textual formats
        fmts = (
            "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
            "%B %d, %Y", "%b %d, %Y",
            "%d %B %Y", "%d %b %Y",
        )
        for fmt in fmts:
            try:
                return _dt.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _month_name_to_number(m: str) -> Optional[int]:
        if not m:
            return None
        try:
            return _dt.strptime(m.strip(), "%B").month
        except Exception:
            try:
                return _dt.strptime(m.strip(), "%b").month
            except Exception:
                return None

    @staticmethod
    def _fmt_full_date(d: _date) -> str:
        """Format as 'Month DD, YYYY' with zero-padded day."""
        return d.strftime("%B %d, %Y")

    @staticmethod
    def _fmt_time_12h(t: Optional[_time]) -> str:
        """Format time as 12-hr 'h:mm am/pm' (lowercase)."""
        if not t:
            return ""
        s = t.strftime("%I:%M %p")  # 01..12
        s = s.lstrip("0")           # -> 1:05 PM
        return s.lower()            # -> 1:05 pm

    @staticmethod
    def _parse_time_any(s: str) -> Optional[_time]:
        """Parse many time styles into a time object."""
        if not s:
            return None
        txt = s.strip().lower()
        txt = re.sub(r"\s+", " ", txt)

        # Normalize "7:6 pm" -> "7:06 pm"
        m = re.match(r"^(\d{1,2}):(\d{1,2})(?::\d{1,2})?\s*([ap]\.?m\.?)?$", txt)
        if m:
            hh, mm, ap = m.groups()
            mm = f"{int(mm):02d}"
            if ap:  # has am/pm
                ap = ap.replace(".", "")
                try:
                    return _dt.strptime(f"{int(hh)}:{mm} {ap}", "%I:%M %p").time()
                except Exception:
                    pass
            else:  # 24h
                try:
                    return _dt.strptime(f"{int(hh):02d}:{mm}", "%H:%M").time()
                except Exception:
                    pass

        # Try a few direct formats
        fmts = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p")
        for fmt in fmts:
            try:
                return _dt.strptime(txt, fmt).time()
            except Exception:
                continue
        return None

    # ---------- DB lookups ----------

    @staticmethod
    def _load_case_datetime_by_case_num(case_num: str) -> Tuple[Optional[_date], Optional[_time]]:
        """Lookup date_filed/time_filed via blotter_case_num."""
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

    @staticmethod
    def _load_case_datetime_from_submission(submission_id: int) -> Tuple[Optional[_date], Optional[_time], Optional[str]]:
        """Returns (case_date_filed, case_time_filed, case_num) for the blotter case owning this submission."""
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

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        """Log/print the final field → value map in the exact order of _KP16_FIELDS."""
        try:
            ordered = {k: out.get(k, "") for k in _KP16_FIELDS}
            print("[KP16] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP16 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP16 logging failed: %s", e)

    # ---------- main ----------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-16 form
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

        # Index answers by lower-cased label & code
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
                kk = k.strip().lower()
                if kk in by_label:
                    return FS.normalize(by_label[kk])
                if kk in by_code:
                    return FS.normalize(by_code[kk])
            return ""

        # Seed direct mappings (raw pulls)
        out: Dict[str, str] = {}
        for target, sources in _KP16_SOURCES.items():
            out[target] = _find_any(sources)

        # Mirror secondary party lines when not provided
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants", "")
        if not (out.get("respondents_two") or "").strip():
            out["respondents_two"] = out.get("respondents", "")

        # ---- Preferred lookup via CASE NUMBER (blotter_case table) ----
        case_num_from_answers = (out.get("brgy_case_num") or "").strip()
        case_date_by_num: Optional[_date] = None
        case_time_by_num: Optional[_time] = None
        if case_num_from_answers:
            case_date_by_num, case_time_by_num = self._load_case_datetime_by_case_num(case_num_from_answers)

        # ---- Fallback: submission_id → blotter_case join ----
        case_date_by_sub, case_time_by_sub, case_num_from_sub = self._load_case_datetime_from_submission(submission_id)

        # If brgy_case_num is blank, also fill from submission-derived case number
        if (not case_num_from_answers) and case_num_from_sub:
            out["brgy_case_num"] = str(case_num_from_sub)

        # DEBUG print/log the raw values fetched from DB (before formatting)
        try:
            print(
                "[KP16][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r"
                % (case_date_by_num, case_time_by_num, case_date_by_sub, case_time_by_sub, case_num_from_sub)
            )
            logger.info(
                "[KP16][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r",
                case_date_by_num, case_time_by_num, case_date_by_sub, case_time_by_sub, case_num_from_sub
            )
        except Exception as _e:
            logger.warning("KP16 raw DB print failed: %s", _e)

        # -------- Date Filed (format: "October 07, 2025") --------
        # Priority: answers (parse) → case by case_num → case by submission → entered trio → today.
        date_answer = (out.get("date_filed") or "").strip()
        date_obj: Optional[_date] = self._try_parse_date(date_answer)

        # If answer is just a day number, compose using month/year entered
        if not date_obj and date_answer.isdigit():
            day_num = int(date_answer)
            m_name = (out.get("month_entered") or "").strip()
            y_txt  = (out.get("year_entered")  or "").strip()
            m_num = self._month_name_to_number(m_name)
            if m_num and y_txt.isdigit():
                try:
                    date_obj = _date(int(y_txt), m_num, day_num)
                except Exception:
                    date_obj = None

        # Fallback to case date by case number
        if not date_obj and isinstance(case_date_by_num, _date):
            date_obj = case_date_by_num

        # Fallback to case date by submission
        if not date_obj and isinstance(case_date_by_sub, _date):
            date_obj = case_date_by_sub

        # Fallback to entered trio if they look usable
        if not date_obj:
            d_txt = (out.get("date_entered") or "").strip()
            m_txt = (out.get("month_entered") or "").strip()
            y_txt = (out.get("year_entered") or "").strip()
            m_num = self._month_name_to_number(m_txt)
            if d_txt.isdigit() and m_num and y_txt.isdigit():
                try:
                    date_obj = _date(int(y_txt), m_num, int(d_txt))
                except Exception:
                    date_obj = None

        # Last resort: today (PH)
        if not date_obj:
            date_obj = _dt.now(ZoneInfo("Asia/Manila")).date()

        out["date_filed"] = self._fmt_full_date(date_obj)

        # -------- Time Filed (format: "h:mm am/pm") --------
        # Priority: answers (parse) → case by case_num → case by submission
        time_answer = (out.get("time_filed") or "").strip()
        t_obj = self._parse_time_any(time_answer)
        if not t_obj and isinstance(case_time_by_num, _time):
            t_obj = case_time_by_num
        if not t_obj and isinstance(case_time_by_sub, _time):
            t_obj = case_time_by_sub
        out["time_filed"] = self._fmt_time_12h(t_obj) if t_obj else ""

        # ---- entered date trio defaults = TODAY (PH) ----
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        # date_entered: ensure it's just a day number (keep original field semantics)
        if not (out.get("date_entered") or "").strip():
            out["date_entered"] = str(today.day)
        else:
            maybe = self._try_parse_date(out["date_entered"])
            if maybe:
                out["date_entered"] = str(maybe.day)

        if not (out.get("month_entered") or "").strip():
            out["month_entered"] = today.strftime("%B")

        if not (out.get("year_entered") or "").strip():
            out["year_entered"] = str(today.year)

        # ---- Final sanitize & ensure all fields exist ----
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP16_FIELDS:
            out.setdefault(k, "")

        # Log what we will fill
        self._log_fill_map(out)

        return out
    