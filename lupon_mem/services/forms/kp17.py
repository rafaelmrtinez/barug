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

logger = logging.getLogger(__name__)

# Exact PDF field names in kp_form_no_17_repudation.pdf
_KP17_FIELDS = [
    "complainants",
    "respondents",
    "respondents_2",
    "brgy_case_num",
    "purpose",
    "date_filed",          # full, e.g., "October 07, 2025"
    "time_filed",          # 12-hr "h:mm am/pm"
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
    "date_filed_2",        # day
    "month_filed",
    "year_filed",
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

    # Filing date/time (answers may provide; DB is source of truth)
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
    # NOTE: allow multiple aliases for the sworn place
    "place_sworned": {"place_sworned", "place_sworn", "place_of_oath", "oath_place"},

    # Chairman / Brgy Captain
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
    "brgy_capt":{"brgy_capt", "barangay captain", "punong barangay", "chairman"},
}

class KP17Handler:
    """
    KP-17: REPUDIATION

    Key behaviors:
      • Pull values by label or field_code.
      • Look up date/time filed from blotter_case using brgy_case_num; fallback to submission-linked case.
      • Log RAW DB date/time fetched.
      • Format date_filed -> "Month DD, YYYY" and time_filed -> "h:mm am/pm".
      • Also fill date_filed_2/month_filed/year_filed from the final date_filed.
      • If secondary party lines are blank, mirror primary ones.
      • Checkbox fields are set to "Yes" if any truthy indicator is present OR details text is provided.
      • Notified and Sworn date trios default to today (PH) if missing/incomplete.
      • Sanitize and ensure all PDF fields exist; log final ordered map.
      • EXTRA LOGGING: dump answers, discovered fields, label/code maps, seed map, fallbacks.
    """

    # -------- helpers: parse/format --------

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

        # ---- Fallback: submission → blotter_case ----
        date_by_sub, time_by_sub, case_num_from_sub = self._load_case_datetime_from_submission(submission_id)

        # If brgy_case_num is blank, also fill from submission-derived case number
        if (not case_num) and case_num_from_sub:
            out["brgy_case_num"] = str(case_num_from_sub)

        # DEBUG: print raw DB values
        try:
            print(
                "[KP17][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r"
                % (date_by_num, time_by_num, date_by_sub, time_by_sub, case_num_from_sub)
            )
            logger.info(
                "[KP17][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r",
                date_by_num, time_by_num, date_by_sub, time_by_sub, case_num_from_sub
            )
        except Exception as _e:
            logger.warning("KP17 raw DB print failed: %s", _e)

        # -------- Date Filed (full + split trio) --------
        date_ans = (out.get("date_filed") or "").strip()
        date_obj: Optional[_date] = self._try_parse_date(date_ans)

        # -------- Ensure place_sworned has a value (prevents KP-17 ValidationError) --------
        if not (out.get("place_sworned") or "").strip():
            out["place_sworned"] = "Barangay Hall of Señor Santo Niño"

        # If answer is just day number, try to build with month/year from notified or filed trios
        if not date_obj and date_ans.isdigit():
            d = int(date_ans)
            m_txt = (out.get("month_filed") or out.get("month_notified") or "").strip()
            y_txt = (out.get("year_filed")  or out.get("year_notified")  or "").strip()
            m_num = self._month_name_to_number(m_txt)
            if m_num and y_txt.isdigit():
                try:
                    date_obj = _date(int(y_txt), m_num, d)
                except Exception:
                    pass

        if not date_obj and isinstance(date_by_num, _date):
            date_obj = date_by_num
        if not date_obj and isinstance(date_by_sub, _date):
            date_obj = date_by_sub

        # Final fallback = today (PH)
        if not date_obj:
            date_obj = _dt.now(ZoneInfo("Asia/Manila")).date()

        out["date_filed"]   = self._fmt_full_date(date_obj)
        out["date_filed_2"] = str(date_obj.day)
        out["month_filed"]  = date_obj.strftime("%B")
        out["year_filed"]   = str(date_obj.year)

        # -------- Time Filed (12-hr) --------
        time_ans = (out.get("time_filed") or "").strip()
        t_obj = self._parse_time_any(time_ans)
        if not t_obj and isinstance(time_by_num, _time):
            t_obj = time_by_num
        if not t_obj and isinstance(time_by_sub, _time):
            t_obj = time_by_sub
        out["time_filed"] = self._fmt_time_12h(t_obj) if t_obj else ""

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

        # -------- Checkbox coercion ("Yes" if true/details present) --------
        def decide_chk(detail_key: str, chk_key: str) -> str:
            detail = (out.get(detail_key) or "").strip()
            chk    = (out.get(chk_key) or "").strip()
            return "Yes" if (self._boolish(chk) or bool(detail)) else ""

        out["fraud_chkbx"]        = decide_chk("fraud_details", "fraud_chkbx")
        out["violence_chkbx"]     = decide_chk("violence_details", "violence_chkbx")
        out["intimidation_chkbx"] = decide_chk("intimidation_details", "intimidation_chkbx")

        # -------- Chairman / Brgy Captain syncing --------
        chair = (out.get("chairman") or "").strip()
        capt  = (out.get("brgy_capt") or "").strip()
        if chair and not capt:
            out["brgy_capt"] = chair
        if capt and not chair:
            out["chairman"] = capt

        # ---- Final sanitize & ensure all fields exist ----
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP17_FIELDS:
            out.setdefault(k, "")

        # Log final map
        self._log_fill_map(out)
        return out
