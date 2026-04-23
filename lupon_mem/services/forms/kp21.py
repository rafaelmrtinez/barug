# lupon_mem/services/forms/kp21.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time
import json, logging

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from .util import get_secretary_name, get_lupon_chair_name
from lupon_mem.services.fields_util import (
    get_latest_form_fields,
    get_field_text,
    get_this_case_kp7_date_filed,
)

logger = logging.getLogger(__name__)

# PDF field names for KP-21
_KP21_FIELDS = [
    "for_complainants","and_complainants","this_date","this_month","this_year",
    "lupon_chairman","complainants","respondents","case_no","purpose",
    "date_filed","time_filed","order_dated",
]

_KP21_SOURCES: Dict[str, Set[str]] = {
    "for_complainants": {"for_complainants","for (complainants)","complainants","complainant(s)","party-complainants","parties_complainants"},
    "and_complainants": {"and_complainants","and (complainants)","complainants","complainant(s)","party-complainants","parties_complainants"},
    "complainants": {"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents": {"respondents","respondent(s)","party-respondents","parties_respondents"},
    "case_no": {"case_no","case_number","brgy_case_number","brgy_case_num","case number","case_num","blotter_case_num","barangay_case_number","barangay case number","barangay case no","brgy case no","barangay case no."},
    "purpose": {"purpose","for","case_purpose"},
    "date_filed": {"date_filed","filed_date","date_of_filing","date_created","date today","date_today"},
    "time_filed": {"time_filed","filed_time","time_of_filing","time_created"},
    "this_date": {"this_date","current_date","date_today","date_entered"},
    "this_month": {"this_month","current_month","month_today","month_entered"},
    "this_year": {"this_year","current_year","year_today","year_entered"},
    "lupon_chairman": {"lupon_chairman","lupon chairman","chairman","punong barangay","barangay captain","brgy_capt"},
    "order_dated": {"order_dated","ordered_date","date_ordered","order dated"},
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

class KP21Handler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP21_FIELDS}
            print("[KP21] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP21 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP21 logging failed: %s", e)

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

        out: Dict[str, str] = {t: find(s) for t, s in _KP21_SOURCES.items()}

        # Case datetime via submission (also get case_id)
        d_by_sub, t_by_sub, case_num_from_sub, case_id = _case_dt_by_submission(submission_id)
        
        # Always ensure case_no is populated from database
        if case_num_from_sub:
            out["case_no"] = str(case_num_from_sub)

        # -------- Pull LATEST KP-7 (PRIMARY SOURCE for filed date/time) --------
        kp7_date_str = None
        kp7_time_obj = None
        
        if case_id:
            try:
                # Use the dedicated function for KP-7 date
                kp7_date_str = get_this_case_kp7_date_filed(case_id)
                
                # Get time from KP-7
                kp7_rows = get_latest_form_fields(case_id, "KP-7")
                if kp7_rows:
                    time_text = get_field_text(kp7_rows, "case_time_filed") or get_field_text(kp7_rows, "time_filed")
                    if time_text:
                        from .kp20b import _parse_time
                        kp7_time_obj = _parse_time(time_text)
            except Exception:
                pass
        
        # -------- date_filed/time_filed MUST come from KP-7 --------
        if kp7_date_str:
            out["date_filed"] = kp7_date_str
        if kp7_time_obj:
            out["time_filed"] = _fmt12(kp7_time_obj)
        
        # date_filed (Month DD, YYYY) - fallback if KP-7 failed
        if not out.get("date_filed"):
            d_obj = d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
            out["date_filed"] = _fmt_full(d_obj)
        
        # time_filed (12h) - fallback if KP-7 failed
        if not out.get("time_filed"):
            out["time_filed"] = _fmt12(t_by_sub) if t_by_sub else ""

        # Current date fields
        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():  out["this_date"]  = str(today.day)
        if not (out.get("this_month") or "").strip(): out["this_month"] = today.strftime("%B")
        if not (out.get("this_year") or "").strip():  out["this_year"]  = str(today.year)

        # Auto-fill lupon_chairman
        if not (out.get("lupon_chairman") or "").strip():
            out["lupon_chairman"] = get_lupon_chair_name(default="")

        # Auto-populate complainants, for_complainants and and_complainants from case data if missing
        if case_id and not out.get("complainants"):
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT complainants FROM blotter_case WHERE blotter_case_id=%s",
                        [case_id]
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        out["complainants"] = FS.sanitize_text(row[0])
            except Exception:
                pass
        
        # Auto-populate respondents from case data if missing
        if case_id and not out.get("respondents"):
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT respondents FROM blotter_case WHERE blotter_case_id=%s",
                        [case_id]
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        out["respondents"] = FS.sanitize_text(row[0])
            except Exception:
                pass
        
        # Auto-populate purpose from case data if missing
        if case_id and not out.get("purpose"):
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT case_purpose FROM blotter_case WHERE blotter_case_id=%s",
                        [case_id]
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        out["purpose"] = FS.sanitize_text(row[0])
            except Exception:
                pass

        # Auto-populate for_complainants and and_complainants with same complainants data
        complainants_text = out.get("complainants", "")
        if complainants_text and not out.get("for_complainants"):
            out["for_complainants"] = complainants_text
        if complainants_text and not out.get("and_complainants"):
            out["and_complainants"] = complainants_text

        # Set default order_dated to today if not provided
        if not out.get("order_dated"):
            out["order_dated"] = _fmt_full(today)

        for k, v in list(out.items()):
            if isinstance(v, str): out[k] = FS.sanitize_text(v)
        for k in _KP21_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-21 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp21_certification_bar_action
            if case_id:
                case_num = out.get("case_no", "")
                notify_kp21_certification_bar_action(case_id, case_num)
        except Exception as e:
            logger.warning("[KP21] Failed to send notifications: %s", e)

        self._log(out)
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
            for pdf_field, source_keys in _KP21_SOURCES.items():
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