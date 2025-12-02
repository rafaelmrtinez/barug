# lupon_mem/services/forms/kp17.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time

import json
import logging
import re

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS
from ..fields_util import (
    get_latest_form_fields,
    get_field_text,
)

logger = logging.getLogger(__name__)

# Exact PDF field names in kp_form_no_17_repudation.pdf
_KP17_FIELDS = [
    "complainants",
    "respondents",
    "respondents_2",
    "brgy_case_num",
    "purpose",
    "date_filed",          # "October 07, 2025"
    "time_filed",          # "h:mm am/pm"
    "fraud_details",
    "fraud_chkbx",
    "violence_chkbx",
    "violence_details",
    "intimidation_details",
    "intimidation_chkbx",
    "date_notified",
    "month_notified",
    "year_notified",
    "complainants_two",
    "date_notified_2",
    "date_sworn",
    "month_sworn",
    "year_sworn",
    "place_sworned",
    "chairman",
    "date_filed_2",        # today (day)
    "month_filed",         # today (Month)
    "year_filed",          # today (YYYY)
    "brgy_capt",
]

# Accept both label text and field_code variants from the builder
_KP17_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants":     {"complainants", "complainant(s)", "party-complainants", "parties_complainants"},
    "complainants_two": {"complainants_two", "complainants 2", "complainant_two", "complainant 2",
                         "additional_complainants", "party-complainants-2"},
    "respondents":      {"respondents", "respondent(s)", "party-respondents", "parties_respondents"},
    "respondents_2":    {"respondents_2", "respondents two", "respondents two line", "respondent_two", "respondent 2",
                         "additional_respondents", "party-respondents-2"},

    # Case number
    "brgy_case_num": {
        "brgy_case_num", "brgy_case_number", "brgy case no.", "brgy case number",
        "barangay case no.", "case number", "case no.", "case_num", "blotter_case_num"
    },

    # Purpose
    "purpose": {"purpose", "for", "case_purpose"},

    # Filing date/time (answers may provide; KP7/DB is source of truth)
    "date_filed": {"date_filed", "filed_date", "date_of_filing", "date created", "date_created", "date_today"},
    "time_filed": {"time_filed", "filed_time", "time_of_filing", "time_created"},

    # Grounds (checkbox + details)
    "fraud_chkbx":        {"fraud_chkbx", "ground_fraud", "is_fraud"},
    "fraud_details":      {"fraud_details", "fraud_desc", "details_fraud"},
    "violence_chkbx":     {"violence_chkbx", "ground_violence", "is_violence"},
    "violence_details":   {"violence_details", "violence_desc", "details_violence"},
    "intimidation_chkbx": {"intimidation_chkbx", "ground_intimidation", "is_intimidation"},
    "intimidation_details":{"intimidation_details", "intimidation_desc", "details_intimidation"},

    # Notified date trio
    "date_notified":  {"date_notified", "notified_date", "date_of_notice"},
    "month_notified": {"month_notified", "notified_month"},
    "year_notified":  {"year_notified", "notified_year"},
    "date_notified_2":{"date_notified_2", "notified_day"},

    # Sworn date trio + place
    "date_sworn":   {"date_sworn", "sworn_day"},
    "month_sworn":  {"month_sworn", "sworn_month"},
    "year_sworn":   {"year_sworn", "sworn_year"},
    "place_sworned": {"place_sworned", "place_sworn", "place_of_oath", "oath_place"},

    # Chairman / Brgy Captain
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
    "brgy_capt":{"brgy_capt", "barangay captain", "punong barangay", "chairman"},
}

class KP17Handler:
    """
    KP-17: REPUDIATION

    Prefers KP-7 for date/time filed:
      • date_filed = KP7.month_created + KP7.date_created + KP7.year_received (swap-tolerant)
      • time_filed = KP7.case_time_filed (rendered as "h:mm am/pm")
    Falls back to blotter_case (by case num, then submission), then to today.
    date_filed_2 / month_filed / year_filed are always today's PH date.
    """

    # -------- helpers: parse/format --------

    @staticmethod
    def _try_parse_date(s: str) -> Optional[_date]:
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
        num = KP17Handler._month_name_to_number(ms)
        if num:
            return _dt(2000, num, 1).strftime("%B")
        return None

    @staticmethod
    def _fmt_full_date(d: _date) -> str:
        return d.strftime("%B %d, %Y")  # Month DD, YYYY

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

    @staticmethod
    def _boolish(v: str) -> bool:
        if not v:
            return False
        t = v.strip().lower()
        return t in {"1","y","yes","true","on","checked","selected","t"}

    # -------- DB lookups --------

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

    # -------- KP-7 helpers via fields_util --------

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
            logger.warning("[KP17] get_latest_form_fields failed: %s", e)
            return None
        if not rows:
            return None
        # Pull by field_code
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

        month_full = KP17Handler._month_to_fullname(m_raw)
        day_int = int(d_raw) if d_raw.isdigit() else None

        # If month invalid and day looks like month text/num, try swap
        if month_full is None and not day_int:
            month_full = KP17Handler._month_to_fullname(d_raw)

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
            ordered = {k: out.get(k, "") for k in _KP17_FIELDS}
            print("[KP17] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP17 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP17 logging failed: %s", e)

    # -------- main --------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)
        print("[KP17][answers_by_id]", json.dumps(answers_by_id, ensure_ascii=False))
        logger.info("[KP17][answers_by_id] %s", json.dumps(answers_by_id, ensure_ascii=False))

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

        print("[KP17][form_fields_raw]", rows)
        logger.info("[KP17][form_fields_raw] %s", rows)

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

        print("[KP17][by_label]", json.dumps(by_label, ensure_ascii=False))
        print("[KP17][by_code]", json.dumps(by_code, ensure_ascii=False))
        logger.info("[KP17][by_label] %s", json.dumps(by_label, ensure_ascii=False))
        logger.info("[KP17][by_code] %s", json.dumps(by_code, ensure_ascii=False))

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
        for target, sources in _KP17_SOURCES.items():
            out[target] = _find_any(sources)

        print("[KP17][seed_out]", json.dumps(out, ensure_ascii=False))
        logger.info("[KP17][seed_out] %s", json.dumps(out, ensure_ascii=False))

        # Mirror secondary party lines when not provided
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants", "")
        if not (out.get("respondents_2") or "").strip():
            out["respondents_2"] = out.get("respondents", "")

        # ---- Preferred lookup via CASE NUMBER (blotter_case table) ----
        case_num = (out.get("brgy_case_num") or "").strip()
        date_by_num, time_by_num = self._load_case_datetime_by_case_num(case_num) if case_num else (None, None)

        # ---- Fallback: submission → blotter_case (also get case_id) ----
        date_by_sub, time_by_sub, case_num_from_sub, case_id = self._load_case_datetime_from_submission(submission_id)

        # If brgy_case_num is blank, also fill from submission-derived case number
        if (not case_num) and case_num_from_sub:
            out["brgy_case_num"] = str(case_num_from_sub)

        # DEBUG: print raw DB values
        try:
            print(
                "[KP17][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r case_id=%r"
                % (date_by_num, time_by_num, date_by_sub, time_by_sub, case_num_from_sub, case_id)
            )
            logger.info(
                "[KP17][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r case_id=%r",
                date_by_num, time_by_num, date_by_sub, time_by_sub, case_num_from_sub, case_id
            )
        except Exception as _e:
            logger.warning("KP17 raw DB print failed: %s", _e)

        # -------- Pull LATEST KP-7 via fields_util (PRIMARY SOURCE) --------
        kp7_date_obj: Optional[_date] = None
        kp7_time_obj: Optional[_time] = None
        kp7_fields = self._kp7_latest_fields(case_id)

        if kp7_fields:
            month_txt = kp7_fields.get("month_created")
            day_txt   = kp7_fields.get("date_created")
            year_txt  = kp7_fields.get("year_received")
            time_txt  = kp7_fields.get("case_time_filed")

            logger.info("[KP17][KP7 latest] month_created=%r date_created=%r year_received=%r case_time_filed=%r",
                        month_txt, day_txt, year_txt, time_txt)

            # Build the date exactly as: MonthName Day, Year (handles swapped inputs)
            kp7_date_obj = self._build_date_from_kp7_fields(month_txt, day_txt, year_txt)

            # Parse time
            if time_txt:
                kp7_time_obj = self._parse_time_any(time_txt)

        # -------- Decide date_filed/time_filed (priority: KP-7 > blotter_case > today) --------
        date_obj: Optional[_date] = kp7_date_obj or (date_by_num if isinstance(date_by_num, _date) else None) or (date_by_sub if isinstance(date_by_sub, _date) else None)
        time_obj: Optional[_time] = kp7_time_obj or (time_by_num if isinstance(time_by_num, _time) else None) or (time_by_sub if isinstance(time_by_sub, _time) else None)

        # Final fallback = today (PH) for the full date (time left blank if none)
        if not date_obj:
            date_obj = _dt.now(ZoneInfo("Asia/Manila")).date()

        out["date_filed"] = self._fmt_full_date(date_obj)
        out["time_filed"] = self._fmt_time_12h(time_obj) if time_obj else ""
        
        # Add complaint date fields from date_filed
        if date_obj:
            out["complaint_date_month"] = date_obj.strftime("%B")
            out["complaint_year"] = str(date_obj.year)
        else:
            out["complaint_date_month"] = ""
            out["complaint_year"] = ""

        # -------- Ensure place_sworned has a value --------
        if not (out.get("place_sworned") or "").strip():
            out["place_sworned"] = "Barangay Hall of Señor Santo Niño"

        # -------- Notified trio defaults --------
        now_ph = _dt.now(ZoneInfo("Asia/Manila")).date()

        d_not = (out.get("date_notified") or "").strip()
        m_not = (out.get("month_notified") or "").strip()
        y_not = (out.get("year_notified") or "").strip()
        if not d_not or not m_not or not y_not:
            out["date_notified"]  = str(now_ph.day)
            out["month_notified"] = now_ph.strftime("%B")
            out["year_notified"]  = str(now_ph.year)
        if not (out.get("date_notified_2") or "").strip():
            out["date_notified_2"] = out.get("date_notified")

        # -------- Sworn trio defaults --------
        d_s = (out.get("date_sworn") or "").strip()
        m_s = (out.get("month_sworn") or "").strip()
        y_s = (out.get("year_sworn") or "").strip()
        if not d_s or not m_s or not y_s:
            out["date_sworn"]  = str(now_ph.day)
            out["month_sworn"] = now_ph.strftime("%B")
            out["year_sworn"]  = str(now_ph.year)

        # -------- Checkbox coercion ("Yes" if checked, display ground names) --------
        grounds = []
        if self._boolish(out.get("fraud_chkbx", "")):
            grounds.append("Fraud")
        if self._boolish(out.get("violence_chkbx", "")):
            grounds.append("Violence")
        if self._boolish(out.get("intimidation_chkbx", "")):
            grounds.append("Intimidation")
        
        out["fraud_chkbx"] = "Yes" if self._boolish(out.get("fraud_chkbx", "")) else ""
        out["violence_chkbx"] = "Yes" if self._boolish(out.get("violence_chkbx", "")) else ""
        out["intimidation_chkbx"] = "Yes" if self._boolish(out.get("intimidation_chkbx", "")) else ""

        # -------- Chairman / Brgy Captain syncing --------
        from .util import get_captain_name
        chair = (out.get("chairman") or "").strip()
        capt  = (out.get("brgy_capt") or "").strip()
        
        # Auto-fill both if empty, using default "LOURDES RAMIREZ"
        if not chair and not capt:
            default_name = get_captain_name(default="LOURDES RAMIREZ")
            out["chairman"] = default_name
            out["brgy_capt"] = default_name
        elif chair and not capt:
            out["brgy_capt"] = chair
        elif capt and not chair:
            out["chairman"] = capt

        # -------- TODAY (PH) split trio for filed date (as requested) --------
        out["date_filed_2"] = str(now_ph.day)
        out["month_filed"]  = now_ph.strftime("%B")
        out["year_filed"]   = str(now_ph.year)

        # ---- Final sanitize & ensure all fields exist ----
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP17_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-17 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp17_repudiation
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [submission_id]
                )
                row = cur.fetchone()
                if row:
                    case_id = row[0]
                    case_num = out.get("brgy_case_num", "")
                    if not case_num:
                        cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                        case_row = cur.fetchone()
                        case_num = case_row[0] if case_row else ""
                    notify_kp17_repudiation(case_id, case_num)
        except Exception as e:
            logger.warning("[KP17] Failed to send notifications: %s", e)

        # Log final map
        self._log_fill_map(out)
        return out
