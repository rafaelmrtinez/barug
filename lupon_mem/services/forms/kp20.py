# lupon_mem/services/forms/kp20.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple, List
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from .util import get_secretary_name, get_lupon_chair_name  # ← auto-fill lupon_sec & chairman
from lupon_mem.services.fields_util import (
    get_latest_form_fields,
    get_field_text,
    get_this_case_kp7_date_filed,
)

logger = logging.getLogger(__name__)

# Exact PDF field names in KP-20 (Certification to File Action)
_KP20_FIELDS = [
    "complainants","respondents","brgy_case_number","purpose",
    "date_filed","time_filed","respondents_2",
    "complaint_date_month","complaint_year","by","ground_of",
    "this_date","this_month","this_year","lupon_sec","chairman",
]

# Accept both label text and field_code variants from the builder
_KP20_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants","complainant(s)","party-complainants","parties_complainants"},
    "respondents": {"respondents","respondent(s)","party-respondents","parties_respondents"},
    "respondents_2":{"respondents","respondent(s)","party-respondents","parties_respondents"},
    "brgy_case_number":{"case_number","brgy_case_number","brgy_case_num","case number","case_no","case_num","blotter_case_num","barangay_case_number","barangay case number","barangay case no","brgy case no"},
    "purpose":{"purpose","for","case_purpose"},
    "date_filed":{"date_filed","filed_date","date_of_filing","date_created","date today","date_today","med_att_date_time_filed","date & time filed","date and time filed"},
    "time_filed":{"time_filed","filed_time","time_of_filing","time_created"},
    "complaint_date_month":{"complaint_date_month","month_of_complaint","current_month","month_today"},
    "complaint_year":{"complaint_year","year_of_complaint","current_year","year_today"},
    # item 4: "by" & "on ground of"
    "by":{"by","issued_by","prepared_by","repudiated_by","affiant","affiant_name"},
    "ground_of":{"ground_of","grounds","reason","basis","repudiation_grounds"},
    # footer dates / signatories
    "this_date":{"this_date","current_date","date_today","date_entered"},
    "this_month":{"this_month","current_month","month_today","month_entered"},
    "this_year":{"this_year","current_year","year_today","year_entered"},
    "lupon_sec":{"lupon_sec","lupon secretary","secretary"},
    "chairman":{"chairman","punong barangay","barangay captain","brgy_capt"},
}

# ---------------- helpers: parse/format ----------------
def _try_parse_date(s: str) -> Optional[_date]:
    if not s:
        return None
    txt = s.strip()
    fmts = (
        "%Y-%m-%d","%m/%d/%Y","%d/%m/%Y",
        "%B %d, %Y","%b %d, %Y",
        "%d %B %Y","%d %b %Y",
        "%d %B, %Y","%d %b, %Y"
    )
    for fmt in fmts:
        try:
            return _dt.strptime(txt, fmt).date()
        except Exception:
            continue
    return None

def _fmt_full(d: _date) -> str:
    return d.strftime("%B %d, %Y")

def _fmt12(t: Optional[_time]) -> str:
    if not t:
        return ""
    return t.strftime("%I:%M %p").lstrip("0").lower()

def _parse_time(s: str) -> Optional[_time]:
    if not s:
        return None
    txt = re.sub(r"\s+"," ", s.strip().lower())
    m = re.match(r"^(\d{1,2}):(\d{1,2})(?::\d{1,2})?\s*([ap]\.?m\.?)?$", txt)
    if m:
        hh, mm, ap = m.groups(); mm = f"{int(mm):02d}"
        if ap:
            ap = ap.replace(".","")
            try:
                return _dt.strptime(f"{int(hh)}:{mm} {ap}", "%I:%M %p").time()
            except Exception:
                pass
        else:
            try:
                return _dt.strptime(f"{int(hh):02d}:{mm}", "%H:%M").time()
            except Exception:
                pass
    for fmt in ("%H:%M","%H:%M:%S","%I:%M %p","%I:%M%p","%I %p"):
        try:
            return _dt.strptime(txt, fmt).time()
        except Exception:
            continue
    return None

def _boolish(v: str) -> bool:
    if not v: return False
    t = v.strip().lower()
    return t in {"1","y","yes","true","on","checked","selected","t"}

# ---------------- DB lookups ----------------
def _case_dt_by_case_num(case_num: str) -> Tuple[Optional[_date], Optional[_time]]:
    if not case_num:
        return None, None
    with connection.cursor() as cur:
        cur.execute(
            "SELECT date_filed, time_filed FROM blotter_case WHERE blotter_case_num=%s LIMIT 1",
            [case_num]
        )
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
            """,
            [submission_id],
        )
        row = cur.fetchone()
    return (row[0], row[1], row[2], row[3]) if row else (None, None, None, None)

def _latest_kp17_submission_id(case_id: int) -> Optional[int]:
    if not case_id:
        return None
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s2.submission_id
              FROM blotter_kp_submission s2
              JOIN kp_form kf ON kf.form_id = s2.form_id
             WHERE s2.blotter_case_id = %s
               AND UPPER(REPLACE(kf.form_code,' ','')) IN ('KP-17','KP17','KP17-REPUDIATION','KP-17-REPUDIATION')
             ORDER BY s2.submitted_at DESC
             LIMIT 1
            """,
            [case_id],
        )
        r = cur.fetchone()
    return int(r[0]) if r else None

def _load_form_label_code_index(form_id: int) -> List[Tuple[int, str, str]]:
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
        return cur.fetchall()

# Pull grounds + who-from KP-17
def _derive_by_and_grounds_from_kp17(kp17_sid: int) -> Tuple[str, str]:
    if not kp17_sid:
        return "", ""

    # 1) Read answers + index the KP-17 form fields (label/code → value)
    answers = FS.load_answers(kp17_sid)
    with connection.cursor() as cur:
        cur.execute("SELECT form_id FROM blotter_kp_submission WHERE submission_id=%s", [kp17_sid])
        row = cur.fetchone()
    if not row:  # safety
        return "", ""
    kp17_form_id = int(row[0])

    rows = _load_form_label_code_index(kp17_form_id)
    by_label: Dict[str, str] = {}
    by_code: Dict[str, str] = {}
    for fid, label, code in rows:
        val = answers.get(str(fid))
        if isinstance(val, str):
            val = FS.sanitize_text(val)
        if val not in (None, "", "null"):
            if label:
                by_label[label.strip().lower()] = val
            if code:
                by_code[code.strip().lower()] = val

    def _find(keys: Set[str]) -> str:
        for k in keys:
            kk = k.strip().lower()
            if kk in by_label: return FS.normalize(by_label[kk])
            if kk in by_code:  return FS.normalize(by_code[kk])
        return ""

    # 2) Heuristics for "by" (the affiant / repudiating party)
    by_keys_primary = {"by", "repudiated_by", "affiant", "affiant_name", "prepared_by", "issued_by"}
    by_txt = _find(by_keys_primary)
    if not by_txt:
        # fallback: use first available party line
        by_txt = _find({"complainants", "complainants_two", "respondents", "respondents_2"})

    # 3) Grounds: build from checkboxes (no details)
    fraud_on  = _find({"fraud_chkbx"})
    viol_on   = _find({"violence_chkbx"})
    intimid_on= _find({"intimidation_chkbx"})
    fraud_det = _find({"fraud_details"})
    viol_det  = _find({"violence_details"})
    intim_det = _find({"intimidation_details"})

    grounds: List[str] = []
    if _boolish(fraud_on) or fraud_det:
        grounds.append("Fraud")
    if _boolish(viol_on) or viol_det:
        grounds.append("Violence")
    if _boolish(intimid_on) or intim_det:
        grounds.append("Intimidation")

    ground_txt = ", ".join([g for g in grounds if g.strip()])
    return (by_txt, ground_txt)

# ---------------- handler ----------------
class KP20Handler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP20_FIELDS}
            print("[KP20] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP20 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP20 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers
        answers = FS.load_answers(submission_id)

        # Discover labels/codes present on this KP-20 form
        rows = _load_form_label_code_index(form_id)

        by_label: Dict[str, str] = {}
        by_code: Dict[str, str] = {}
        for fid, label, code in rows:
            v = answers.get(str(fid))
            if isinstance(v, str):
                v = FS.sanitize_text(v)
            if v not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = v
                if code:
                    by_code[code.strip().lower()] = v

        def find(keys: Set[str]) -> str:
            for k in keys:
                kk = k.strip().lower()
                if kk in by_label: return FS.normalize(by_label[kk])
                if kk in by_code:  return FS.normalize(by_code[kk])
            return ""

        # Seed direct mappings
        out: Dict[str, str] = {t: find(s) for t, s in _KP20_SOURCES.items()}

        # Case datetime via case number or submission (also get case_id)
        case_num = (out.get("brgy_case_number") or "").strip()
        d_by_num, t_by_num = _case_dt_by_case_num(case_num) if case_num else (None, None)
        d_by_sub, t_by_sub, case_num_from_sub, case_id = _case_dt_by_submission(submission_id)
        
        # Always ensure brgy_case_number is populated from database
        if case_num_from_sub:
            out["brgy_case_number"] = str(case_num_from_sub)

        # -------- Pull LATEST KP-7 (PRIMARY SOURCE for filed date/time) --------
        kp7_date_str = None
        kp7_time_obj = None
        
        # First check if date_filed already has the combined format "Jan 28, 2026 @03:09 PM"
        date_filed_raw = out.get("date_filed", "").strip()
        if date_filed_raw and "@" in date_filed_raw:
            # Split "Jan 28, 2026 @03:09 PM" into date and time parts
            parts = date_filed_raw.split("@")
            if len(parts) == 2:
                date_part = parts[0].strip()
                time_part = parts[1].strip()
                
                # Parse and reformat date to "January 28, 2026"
                date_obj = _try_parse_date(date_part)
                if date_obj:
                    kp7_date_str = _fmt_full(date_obj)
                
                # Parse time
                kp7_time_obj = _parse_time(time_part)
        
        # If not found in saved answers, try KP-7 form
        if not kp7_date_str and case_id:
            try:
                kp7_date_str = get_this_case_kp7_date_filed(case_id)
                
                # Get time from KP-7
                kp7_rows = get_latest_form_fields(case_id, "KP-7")
                if kp7_rows:
                    time_text = get_field_text(kp7_rows, "case_time_filed") or get_field_text(kp7_rows, "time_filed")
                    if time_text:
                        kp7_time_obj = _parse_time(time_text)
            except Exception as e:
                pass
        
        # -------- date_filed/time_filed MUST come from KP-7 or saved answers --------
        if kp7_date_str:
            out["date_filed"] = kp7_date_str
        if kp7_time_obj:
            out["time_filed"] = _fmt12(kp7_time_obj)
        
        # date_filed (Month DD, YYYY) - fallback if KP-7 failed
        if not out.get("date_filed"):
            d_obj = d_by_num or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
            out["date_filed"] = _fmt_full(d_obj)
        
        # time_filed (12h) - fallback if KP-7 failed
        if not out.get("time_filed"):
            t_ans = (out.get("time_filed") or "").strip()
            t_obj = _parse_time(t_ans) or t_by_num or t_by_sub
            out["time_filed"] = _fmt12(t_obj) if t_obj else ""

        # Complaint month/year → use same date as date_filed
        date_filed_str = out.get("date_filed", "")
        if date_filed_str:
            date_obj = _try_parse_date(date_filed_str)
            if date_obj:
                out["complaint_date_month"] = f"{date_obj.strftime('%B')} {date_obj.day}"
                out["complaint_year"] = str(date_obj.year)

        # -------- Item 4: BY + GROUNDS (derive from latest KP-17 if missing) --------
        kp17_sid = _latest_kp17_submission_id(case_id) if case_id else None
        if (not (out.get("by") or "").strip()) or (not (out.get("ground_of") or "").strip()):
            by_from_kp17, grounds_from_kp17 = _derive_by_and_grounds_from_kp17(kp17_sid) if kp17_sid else ("", "")
            if not (out.get("by") or "").strip():
                out["by"] = by_from_kp17 or out.get("by", "")
            if not (out.get("ground_of") or "").strip():
                out["ground_of"] = grounds_from_kp17 or out.get("ground_of", "")

        # “THIS” date trio defaults to today (PH)
        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        if not (out.get("this_date") or "").strip():
            out["this_date"] = str(today.day)
        else:
            maybe = _try_parse_date(out["this_date"])
            if maybe: out["this_date"] = str(maybe.day)
        if not (out.get("this_month") or "").strip():
            out["this_month"] = today.strftime("%B")
        if not (out.get("this_year") or "").strip():
            out["this_year"] = str(today.year)

        # --- Auto-fill signatories ---
        if not (out.get("lupon_sec") or "").strip():
            out["lupon_sec"] = get_secretary_name(default=out.get("lupon_sec",""))
        if not (out.get("chairman") or "").strip():
            out["chairman"] = get_lupon_chair_name(default=out.get("chairman",""))

        # sanitize + ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP20_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-20 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp20_certification_file_action
            if case_id:
                case_num = out.get("brgy_case_number", "")
                notify_kp20_certification_file_action(case_id, case_num)
        except Exception as e:
            logger.warning("[KP20] Failed to send notifications: %s", e)

        # Final ordered log of exactly what goes into the PDF
        self._log(out)
        return out
