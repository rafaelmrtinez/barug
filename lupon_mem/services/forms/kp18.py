# lupon_mem/services/forms/kp18.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time

import json
import logging
import re

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS
from .util import get_lupon_chair_name  # Pangkat Chairman (Lupon Chair/President)
from ..fields_util import (
    get_latest_form_fields,
    get_field_text,
)

logger = logging.getLogger(__name__)

# Exact PDF field names in kp_form_no_18_notice_of_hearing.pdf
_KP18_FIELDS = [
    "complainants",
    "respondents",
    "brgy_case_number",
    "purpose",
    "date_filed",
    "time_filed",
    "respondents_two",
    "notice_date",
    "notice_month",
    "notice_year",
    "notice_time",
    "hearing_schedule",         # "Month DD" (e.g., "October 20")
    "hearing_schedule_year",    # "YYYY" (e.g., "2025")
    "this_date",
    "this_month",
    "this_year",
    "chairman",                 # Pangkat Chairman
    "date_notified",
    "month_notified",
    "year_notified",
    "complainants_two",
    "respondents_three",
]

# Accept both label text and field_code variants from the builder
_KP18_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants":     {"complainants", "complainant(s)", "party-complainants", "parties_complainants"},
    "complainants_two": {"complainants_two", "complainants 2", "complainant_two", "complainant 2",
                         "additional_complainants", "party-complainants-2"},
    "respondents":      {"respondents", "respondent(s)", "party-respondents", "parties_respondents"},
    "respondents_two":  {"respondents_two", "respondents 2", "respondent_two", "respondent 2",
                         "additional_respondents", "party-respondents-2"},
    "respondents_three":{"respondents_three", "respondents 3", "respondent_three", "respondent 3"},

    # Case number
    "brgy_case_number": {
        "brgy_case_number", "brgy_case_num", "brgy case no.", "brgy case number",
        "barangay case no.", "case number", "case_no", "case num", "case_num", "blotter_case_num"
    },

    # Purpose
    "purpose": {"purpose", "for", "case_purpose"},

    # Filing date/time (answers may provide; KP7/DB is source of truth)
    "date_filed": {"date_filed", "filed_date", "date_of_filing", "date created", "date_created", "date_today"},
    "time_filed": {"time_filed", "filed_time", "time_of_filing", "time_created"},

    # Notice trio comes from form UI inputs
    "notice_date":  {"notice_date", "notice_day", "day_notice"},
    "notice_month": {"notice_month", "month_notice"},
    "notice_year":  {"notice_year", "year_notice"},
    "notice_time":  {"notice_time", "time_notice"},

    # Hearing schedule header (duplicate on some forms)
    "hearing_schedule":       {"hearing_schedule", "appearance_month", "hearing_month", "schedule_month"},
    "hearing_schedule_year":  {"hearing_schedule_year", "appearance_year", "hearing_year", "schedule_year", "current_year"},

    # Entered “this” date trio
    "this_date":  {"this_date", "date_entered", "current_date", "date_today", "date_created"},
    "this_month": {"this_month", "month_entered", "current_month", "month_today", "month_created"},
    "this_year":  {"this_year", "year_entered", "current_year", "year_today", "year_created"},

    # Notified date trio (service)
    "date_notified":  {"date_notified", "served_date", "service_date"},
    "month_notified": {"month_notified", "served_month", "service_month"},
    "year_notified":  {"year_notified", "served_year", "service_year"},

    # Chairman (we will override to Pangkat Chair automatically if blank)
    "chairman": {},
}

class KP18Handler:
    """
    KP-18: NOTICE OF HEARING

    Behavior:
      • Prefer KP-7 for date/time filed:
          - date_filed = KP7.month_created + KP7.date_created + KP7.year_received
          - time_filed = KP7.case_time_filed (fallback: KP7.time_filed)
      • If KP-7 missing -> fall back to blotter_case (by case no. then submission), then to TODAY (PH).
      • Notice date trio (notice_date/month/year) is derived from the same date_obj used for date_filed.
      • Hearing schedule header uses newest hearing_date from fn_case_mediation_hearings(case_id); fallback to notice date.
      • Auto-fill chairman with Pangkat Chairman.
      • Mirror missing secondary party lines.
      • “this_*” & notified trios default to TODAY (PH).
    """

    # ---------- helpers ----------

    @staticmethod
    def _try_parse_date(s: str) -> _date | None:
        if not s:
            return None
        txt = s.strip()
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
    def _month_to_fullname(m: str) -> Optional[str]:
        """Accept '10', 'Oct', 'October' -> 'October'."""
        if not m:
            return None
        ms = m.strip()
        if ms.isdigit():
            try:
                return _dt(2000, int(ms), 1).strftime("%B")
            except Exception:
                return None
        try_num = KP18Handler._month_name_to_number(ms)
        if try_num:
            return _dt(2000, try_num, 1).strftime("%B")
        return None

    @staticmethod
    def _fmt_full_date(d: _date) -> str:
        return d.strftime("%B %d, %Y")

    @staticmethod
    def _fmt_time_12h(t: Optional[_time]) -> str:
        if not t:
            return ""
        s = t.strftime("%I:%M %p")
        s = s.lstrip("0")
        return s.lower()

    @staticmethod
    def _parse_time_any(s: str) -> Optional[_time]:
        if not s:
            return None
        txt = re.sub(r"\s+", " ", s.strip().lower())
        m = re.match(r"^(\d{1,2}):(\d{1,2})(?::\d{1,2})?\s*([ap]\.?m\.?)?$", txt)
        if m:
            hh, mm, ap = m.groups()
            mm = f"{int(mm):02d}"
            if ap:
                ap = ap.replace(".", "")
                try:
                    return _dt.strptime(f"{int(hh)}:{mm} {ap}", "%I:%M %p").time()
                except Exception:
                    pass
            else:
                try:
                    return _dt.strptime(f"{int(hh):02d}:{mm}", "%H:%M").time()
                except Exception:
                    pass
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p"):
            try:
                return _dt.strptime(txt, fmt).time()
            except Exception:
                continue
        return None

    # ---------- DB lookups ----------

    @staticmethod
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

    @staticmethod
    def _load_case_datetime_from_submission(submission_id: int) -> Tuple[Optional[_date], Optional[_time], Optional[str], Optional[int]]:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT bc.date_filed, bc.time_filed, bc.blotter_case_num, bc.blotter_case_id
                  FROM blotter_kp_submission s
                  JOIN blotter_case bc ON bc.blotter_case_id = s.blotter_case_id
                 WHERE s.submission_id = %s
                """,
                [submission_id],
            )
            row = cur.fetchone()
        if not row:
            return None, None, None, None
        return row[0], row[1], row[2], row[3]

    @staticmethod
    def _latest_hearing_date_for_case(case_id: int) -> Optional[_date]:
        """
        Get newest hearing_date from fn_case_mediation_hearings(case_id).
        """
        if not case_id:
            return None
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT hearing_date
                  FROM fn_case_mediation_hearings(%s)
                 WHERE COALESCE(NULLIF(TRIM(hearing_date), ''), NULL) IS NOT NULL
                 ORDER BY (hearing_date)::date DESC, notice_created_at DESC
                 LIMIT 1
                """,
                [case_id],
            )
            row = cur.fetchone()
        if not row:
            return None
        txt = str(row[0]).strip()
        try:
            return _dt.strptime(txt, "%Y-%m-%d").date()
        except Exception:
            pass
        return KP18Handler._try_parse_date(txt)

    # ---------- KP-7 helpers via fields_util ----------

    @staticmethod
    def _kp7_latest_fields(case_id: Optional[int]) -> Optional[Dict[str, Optional[str]]]:
        """
        Use fields_util.get_latest_form_fields(case_id, 'KP-7') and return a tiny map of relevant codes.
        Returns dict with keys: month_created, date_created, year_received, case_time_filed (values may be None).
        """
        if not case_id:
            return None
        try:
            rows = get_latest_form_fields(case_id, 'KP-7')
        except Exception as e:
            logger.warning("[KP18] get_latest_form_fields failed: %s", e)
            return None
        if not rows:
            return None
        month_created = get_field_text(rows, "month_created")
        date_created  = get_field_text(rows, "date_created")
        year_received = get_field_text(rows, "year_received")
        time_filed    = get_field_text(rows, "case_time_filed") or get_field_text(rows, "time_filed")
        return {
            "month_created": month_created,
            "date_created": date_created,
            "year_received": year_received,
            "case_time_filed": time_filed,
        }

    @staticmethod
    def _build_date_from_kp7_fields(month_txt: Optional[str], day_txt: Optional[str], year_txt: Optional[str]) -> Optional[_date]:
        """
        Build a date from KP-7 pieces, tolerating swapped inputs:
          - month_txt may be "October", "Oct", or "10" (also accidentally "29")
          - day_txt may be "29" (also accidentally "October")
          - year_txt must be 4-digit numeric
        Returns a date or None if impossible.
        """
        m_raw = (month_txt or "").strip()
        d_raw = (day_txt or "").strip()
        y_raw = (year_txt or "").strip()

        if not (y_raw.isdigit() and len(y_raw) == 4):
            return None
        year = int(y_raw)

        month_full = KP18Handler._month_to_fullname(m_raw)
        day_int = int(d_raw) if d_raw.isdigit() else None

        # If month invalid and day looks like month text/num, try swap
        if month_full is None and not day_int:
            month_full = KP18Handler._month_to_fullname(d_raw)

        # If still no day, check if m_raw is actually a day number
        if day_int is None and m_raw.isdigit():
            try:
                v = int(m_raw)
                if 1 <= v <= 31:
                    day_int = v
            except Exception:
                pass

        if not month_full or not day_int:
            return None

        try:
            month_num = _dt.strptime(month_full, "%B").month
            return _date(year, month_num, day_int)
        except Exception:
            return None

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP18_FIELDS}
            print("[KP18] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP18 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP18 logging failed: %s", e)

    # ---------- main ----------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this form
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
        for target, sources in _KP18_SOURCES.items():
            out[target] = _find_any(sources)

        # Mirror secondary party lines if blank
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants", "")
        if not (out.get("respondents_two") or "").strip():
            out["respondents_two"] = out.get("respondents", "")
        if not (out.get("respondents_three") or "").strip():
            out["respondents_three"] = out.get("respondents", "")

        # ---- Case date/time via case number, then submission (also get case_id) ----
        case_num = (out.get("brgy_case_number") or "").strip()
        date_by_num, time_by_num = self._load_case_datetime_by_case_num(case_num) if case_num else (None, None)
        date_by_sub, time_by_sub, case_num_from_sub, case_id = self._load_case_datetime_from_submission(submission_id)

        # If brgy_case_number is blank, fill from submission-derived case number
        if (not case_num) and case_num_from_sub:
            out["brgy_case_number"] = str(case_num_from_sub)

        # -------- Pull LATEST KP-7 (PRIMARY SOURCE for filed date/time) --------
        kp7_date_obj: Optional[_date] = None
        kp7_time_obj: Optional[_time] = None
        kp7_fields = self._kp7_latest_fields(case_id)

        if kp7_fields:
            month_txt = kp7_fields.get("month_created")
            day_txt   = kp7_fields.get("date_created")
            year_txt  = kp7_fields.get("year_received")
            time_txt  = kp7_fields.get("case_time_filed")

            logger.info("[KP18][KP7 latest] month_created=%r date_created=%r year_received=%r case_time_filed=%r",
                        month_txt, day_txt, year_txt, time_txt)

            kp7_date_obj = self._build_date_from_kp7_fields(month_txt, day_txt, year_txt)
            if time_txt:
                kp7_time_obj = self._parse_time_any(time_txt)

        # -------- date_filed/time_filed MUST come from KP-7 --------
        if kp7_date_obj:
            out["date_filed"] = self._fmt_full_date(kp7_date_obj)
        if kp7_time_obj:
            out["time_filed"] = self._fmt_time_12h(kp7_time_obj)

        # -------- Process notice fields from form UI --------
        # Parse notice_date if it's a full date string
        notice_date_raw = out.get("notice_date", "")
        if notice_date_raw:
            parsed_date = self._try_parse_date(notice_date_raw)
            if parsed_date:
                out["notice_date"] = str(parsed_date.day)
                out["notice_month"] = parsed_date.strftime("%B")
                out["notice_year"] = str(parsed_date.year)
        
        # Format notice_time to 12-hour format
        notice_time_raw = out.get("notice_time", "")
        if notice_time_raw:
            parsed_time = self._parse_time_any(notice_time_raw)
            if parsed_time:
                out["notice_time"] = self._fmt_time_12h(parsed_time)

        # ---- Hearing schedule header: LATEST hearing date via function; fallback to notice date --------
        latest_hearing: Optional[_date] = self._latest_hearing_date_for_case(case_id) if case_id else None
        if latest_hearing:
            out["hearing_schedule"] = f"{latest_hearing.strftime('%B')} {latest_hearing.day}"
            out["hearing_schedule_year"] = str(latest_hearing.year)
        else:
            notice_month = out.get("notice_month", "")
            notice_day = out.get("notice_date", "")
            notice_year = out.get("notice_year", "")
            if notice_month and notice_day:
                out["hearing_schedule"] = f"{notice_month} {notice_day}"
            if notice_year:
                out["hearing_schedule_year"] = notice_year

        # -------- “THIS” date trio (entered) defaults to today --------
        ph_today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():
            out["this_date"] = str(ph_today.day)
        else:
            maybe = self._try_parse_date(out["this_date"])
            if maybe:
                out["this_date"] = str(maybe.day)

        if not (out.get("this_month") or "").strip():
            out["this_month"] = ph_today.strftime("%B")

        if not (out.get("this_year") or "").strip():
            out["this_year"] = str(ph_today.year)

        # -------- Notified (service) date trio defaults --------
        if not (out.get("date_notified") or "").strip():
            out["date_notified"] = str(ph_today.day)
        else:
            maybe = self._try_parse_date(out["date_notified"])
            if maybe:
                out["date_notified"] = str(maybe.day)

        if not (out.get("month_notified") or "").strip():
            out["month_notified"] = ph_today.strftime("%B")

        if not (out.get("year_notified") or "").strip():
            out["year_notified"] = str(ph_today.year)

        # -------- Pangkat Chairman (auto-fill like KP-13) --------
        if not (out.get("chairman") or "").strip():
            out["chairman"] = get_lupon_chair_name(default=out.get("chairman", ""))

        # ---- Final sanitize & ensure all fields exist ----
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP18_FIELDS:
            out.setdefault(k, "")

        # Log final map
        self._log_fill_map(out)
        return out
