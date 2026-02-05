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
from .util import get_lupon_chair_name, get_case_time_filed_from_kp7

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
    "chairman",                # should print Lupon/Pangkat Chairman
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
    "kp7_date_time_filed": {"date & time filed case", "date and time filed case", "kp7_date_time_filed", "date_time_filed"},

    # Settlement text
    "settlement_statement": {
        "settlement_statement", "amicable_settlement", "settlement_terms", "agreement_terms",
        "details_of_settlement", "narrative", "description"
    },

    # Entered date trio
    "date_entered":  {"date_entered", "current_date", "this_date", "date_today", "date_created"},
    "month_entered": {"month_entered", "current_month", "month_today", "month_created"},
    "year_entered":  {"year_entered", "current_year", "year_today", "year_created"},
    
    # Processed date (source for date_entered/month_entered/year_entered)
    "processed_on_date": {"processed_on_date", "processed on (date)", "date_processed"},

    # Chairman (the PDF field key is “chairman”; we will fill Lupon/Pangkat Chair)
    "chairman": {"pangkat chairman", "lupon chair", "lupon chairman","punong barangay", "brgy_capt"},
}


class KP16Handler:
    """
    KP-16: AMICABLE SETTLEMENT

    Behavior:
      • Pull values from saved answers by label or field_code (robust to common variants).
      • If complainants_two/respondents_two are blank, mirror the primary lines.
      • date_filed:
           - Prefer by matching brgy_case_num against blotter_case.blotter_case_num.
           - Else fall back to submission → blotter_case join.
           - Else compose from (date_entered, month_entered, year_entered) or PH today.
           - Always format "Month DD, YYYY".
      • time_filed:
           - Same lookup preference as date.
           - Always format 12-hr "h:mm am/pm" (lowercase).
      • Chairman:
           - If blank, auto-fill with Lupon/Pangkat Chairman (role name: BARANGAY LUPON PRESIDENT).
      • Logs raw DB values and final ordered fill map.
    """

    # ---------- parsing / formatting helpers ----------

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
        return d.strftime("%B %d, %Y")

    @staticmethod
    def _fmt_time_12h(t: Optional[_time]) -> str:
        if not t:
            return ""
        s = t.strftime("%I:%M %p")  # 01..12
        s = s.lstrip("0")
        return s.lower()            # e.g., "7:06 pm"

    @staticmethod
    def _parse_time_any(s: str) -> Optional[_time]:
        if not s:
            return None
        txt = s.strip().lower()
        txt = re.sub(r"\s+", " ", txt)

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
            ordered = {k: out.get(k, "") for k in _KP16_FIELDS}
            print("[KP16] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP16 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP16 logging failed: %s", e)

    # ---------- main ----------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

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

        out: Dict[str, str] = {}
        for target, sources in _KP16_SOURCES.items():
            out[target] = _find_any(sources)

        # Mirror second lines if blank
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants", "")
        if not (out.get("respondents_two") or "").strip():
            out["respondents_two"] = out.get("respondents", "")

        # Prefer case number lookup
        case_num_from_answers = (out.get("brgy_case_num") or "").strip()
        case_date_by_num: Optional[_date] = None
        case_time_by_num: Optional[_time] = None
        if case_num_from_answers:
            case_date_by_num, case_time_by_num = self._load_case_datetime_by_case_num(case_num_from_answers)

        # Fallback via submission
        case_date_by_sub, case_time_by_sub, case_num_from_sub = self._load_case_datetime_from_submission(submission_id)
        if (not case_num_from_answers) and case_num_from_sub:
            out["brgy_case_num"] = str(case_num_from_sub)

        try:
            print("[KP16][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r"
                  % (case_date_by_num, case_time_by_num, case_date_by_sub, case_time_by_sub, case_num_from_sub))
            logger.info("[KP16][DB RAW] by_case_num: date=%r time=%r ; by_submission: date=%r time=%r case_num=%r",
                        case_date_by_num, case_time_by_num, case_date_by_sub, case_time_by_sub, case_num_from_sub)
        except Exception as _e:
            logger.warning("KP16 raw DB print failed: %s", _e)

        # ---- Date Filed and Time Filed from blotter_case ----
        date_obj: Optional[_date] = None
        time_obj: Optional[_time] = None
        
        # Get date_filed and time_filed directly from blotter_case table
        if isinstance(case_date_by_sub, _date):
            date_obj = case_date_by_sub
        if isinstance(case_time_by_sub, _time):
            time_obj = case_time_by_sub
        
        logger.info("[KP16] Using blotter_case date_filed=%s time_filed=%s", date_obj, time_obj)
        
        # Fallback logic if blotter_case doesn't have the values
        if not date_obj:
            date_answer = (out.get("date_filed") or "").strip()
            date_obj = self._try_parse_date(date_answer)

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

            if not date_obj and isinstance(case_date_by_num, _date):
                date_obj = case_date_by_num
            if not date_obj and isinstance(case_date_by_sub, _date):
                date_obj = case_date_by_sub
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
            if not date_obj:
                date_obj = _dt.now(ZoneInfo("Asia/Manila")).date()

        out["date_filed"] = self._fmt_full_date(date_obj)
        
        # Use time from blotter_case
        if not time_obj:
            time_obj = case_time_by_num if case_time_by_num else None
        out["time_filed"] = self._fmt_time_12h(time_obj)

        # ---- entered date trio: extract from processed_on_date if available ----
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()
        
        # Check if processed_on_date exists in answers
        processed_date_str = _find_any({"processed_on_date", "processed on (date)", "date_processed"})
        processed_date_obj = self._try_parse_date(processed_date_str) if processed_date_str else None
        
        # Use processed_on_date if available, otherwise use today
        source_date = processed_date_obj if processed_date_obj else today

        if not (out.get("date_entered") or "").strip():
            out["date_entered"] = str(source_date.day)
        else:
            maybe = self._try_parse_date(out["date_entered"])
            if maybe:
                out["date_entered"] = str(maybe.day)

        if not (out.get("month_entered") or "").strip():
            out["month_entered"] = source_date.strftime("%B")

        if not (out.get("year_entered") or "").strip():
            out["year_entered"] = str(source_date.year)

        # ---- Chairman → Barangay Captain ----
        if not (out.get("chairman") or "").strip():
            from .util import get_captain_name
            out["chairman"] = get_captain_name(default=out.get("chairman", ""))

        # ---- Final sanitize & ensure all fields exist ----
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP16_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-16 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp16_amicable_settlement
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
                    notify_kp16_amicable_settlement(case_id, case_num)
        except Exception as e:
            logger.warning("[KP16] Failed to send notifications: %s", e)

        self._log_fill_map(out)
        return out

    def persist_computed(self, *, form_id: int, submission_id: int, case_id: int, out_map: dict) -> None:
        """Save computed values back to the database."""
        import json as _json
        
        # Get field mappings for this form
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT kff.field_id, LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                       LOWER(f.field_code) AS code
                  FROM kp_form_field kff
                  JOIN kp_field f ON f.field_id = kff.field_id
                 WHERE kff.form_id = %s
                """,
                [form_id],
            )
            rows = cur.fetchall()
        
        # Create reverse mapping from PDF field names to database field_ids
        field_mapping = {}
        for field_id, label, code in rows:
            label_lower = (label or "").strip().lower()
            code_lower = (code or "").strip().lower()
            
            # Map PDF field names to database field_ids
            for pdf_field, source_keys in _KP16_SOURCES.items():
                if label_lower in source_keys or code_lower in source_keys:
                    field_mapping[pdf_field] = field_id
                    break
        
        # Save computed values to database
        with connection.cursor() as cur:
            for pdf_field, value in out_map.items():
                if pdf_field in field_mapping and value:
                    field_id = field_mapping[pdf_field]
                    cur.execute(
                        """
                        INSERT INTO blotter_kp_answer (submission_id, field_id, value_json)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (submission_id, field_id)
                        DO UPDATE SET value_json = EXCLUDED.value_json
                        """,
                        [submission_id, field_id, _json.dumps(value)]
                    )
