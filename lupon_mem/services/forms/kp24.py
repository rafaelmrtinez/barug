# lupon_mem/services/forms/kp24.py
from __future__ import annotations
from typing import Dict, Set, Optional, Tuple
from datetime import datetime as _dt, date as _date, time as _time
import json, logging, re

from django.db import connection
from zoneinfo import ZoneInfo
from .. import form_shared as FS
from .util import get_lupon_chair_name

logger = logging.getLogger(__name__)

# --- Exact PDF fields in kp_form_no_24.pdf ---
_KP24_FIELDS = [
    "complaints", "respondents", "case_num", "purpose",
    "date_filed", "time_filed", "time_filed_2",
    "complaints_two", "respondents_two",
    "motion_date", "motion_month", "motion_year", "motion_time",
    "filed_by", "this_date", "chairman", "this_year",
    "complainants_sig", "respondents_sig",
]

# Sources we accept (labels or field_code), all compared lowercased
_KP24_SOURCES: Dict[str, Set[str]] = {
    # Complainants: include possessive label variants
    "complaints": {
        "complainants", "complainant(s)", "complainant",
        "complainants_2", "party-complainants", "parties_complainants",
        "complaints",
        "complainant's", "complainant’s",
    },
    "respondents": {
        "respondents", "respondent(s)", "respondent",
        "party-respondents", "parties_respondents",
    },
    "case_num": {"case_num","case_no","brgy_case_num","brgy_case_number","blotter_case_num"},
    "purpose":  {"purpose","for","case_purpose"},

    "date_filed":   {"date_filed","filed_date","date_of_filing","date_created"},
    "time_filed":   {"time_filed","filed_time","time_of_filing","time_created"},

    # NOTE: per instruction, this visual field should contain the complainants name.
    # We still keep a source set, but the code below will force-fill from complaints.
    "time_filed_2": {
        "complainants", "complainant(s)", "complainant",
        "complainants_2", "party-complainants", "parties_complainants",
        "complaints", "complainant's", "complainant’s",
    },

    # Motion date notes:
    #   - If "2025-10-31" provided, set motion_date="31", motion_month="OCTOBER", motion_year="2025"
    #   - motion_time 12h am/pm
    "motion_date":  {"motion_date","order_dated","ordered_date"},
    "motion_month": {"motion_month"},
    "motion_year":  {"motion_year"},
    "motion_time":  {"motion_time","hearing_time"},

    # “Filed by” (override from kp23_filing if blank)
    "filed_by": {"filed_by","prepared_by","issued_by","kp23_filed_by"},

    # Today fields come from current date
    "this_date": set(),
    "chairman":  set(),
    "this_year": set(),

    # Signatures
    "complainants_sig": {},
    "respondents_sig":  {
        "respondents", "respondent(s)", "respondent",
        "party-respondents", "parties_respondents"
    },
}

# ----------------- helpers -----------------

def _try_parse_date(s: str) -> Optional[_date]:
    if not s: return None
    txt = s.strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y",
                "%B %d, %Y","%b %d, %Y","%d %B %Y","%d %b %Y"):
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

def _case_ctx_by_submission(submission_id: int) -> Tuple[Optional[_date], Optional[_time], Optional[str], Optional[int]]:
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

# ---- KP-23 meta → who filed ----
def _person_full_name(pid: int) -> str:
    if not pid: return ""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(TRIM(first_name),''), COALESCE(TRIM(middle_name),''), 
                   COALESCE(TRIM(last_name),''),  COALESCE(TRIM(suffix),'')
              FROM person WHERE person_id=%s
        """,[pid])
        r = cur.fetchone()
    if not r: return ""
    fn, mn, ln, sx = r
    return FS.normalize(" ".join(x for x in [fn, mn, ln, sx] if x).strip())

def _latest_kp23_filer_name_for_case(case_id: int) -> str:
    if not case_id: return ""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT k.party_person_id
              FROM kp23_filing k
              JOIN blotter_kp_submission s ON s.submission_id = k.submission_id
             WHERE k.blotter_case_id=%s
             ORDER BY COALESCE(s.submitted_at, k.created_at) DESC
             LIMIT 1
        """,[case_id])
        r = cur.fetchone()
    return _person_full_name(r[0]) if r else ""

# ---- Party names fallback (from case) ----
def _party_names_for_case(case_id: int, side: str) -> str:
    if not case_id: return ""
    if side == "C":
        sql = """
          SELECT p.first_name, p.middle_name, p.last_name, p.suffix
            FROM complainant_case c JOIN person p ON p.person_id=c.person_id
           WHERE c.blotter_case_id=%s ORDER BY p.last_name, p.first_name
        """
    else:
        sql = """
          SELECT p.first_name, p.middle_name, p.last_name, p.suffix
            FROM respondent_case r JOIN person p ON p.person_id=r.person_id
           WHERE r.blotter_case_id=%s ORDER BY p.last_name, p.first_name
        """
    with connection.cursor() as cur:
        cur.execute(sql, [case_id])
        rows = cur.fetchall() or []
    names = [
        " ".join(x for x in [fn or "", mn or "", ln or "", sx or ""] if x).strip()
        for fn, mn, ln, sx in rows
    ]
    return FS.normalize(", ".join(n for n in names if n))

# ---------------- main handler ----------------

class KP24Handler:
    @staticmethod
    def _log(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP24_FIELDS}
            print("[KP24] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP24 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP24 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)

        # Discover available labels/codes for this form
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

        by_label: Dict[str,str] = {}
        by_code:  Dict[str,str] = {}
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

        # Base map from answers/prefills
        out: Dict[str,str] = {t: find(s) for t, s in _KP24_SOURCES.items()}

        # Case context
        d_by_sub, t_by_sub, case_num, case_id = _case_ctx_by_submission(submission_id)
        if not (out.get("case_num") or "").strip() and case_num:
            out["case_num"] = str(case_num)

        # Parties — fallback from DB if still blank
        if not (out.get("complaints") or "").strip():
            out["complaints"] = _party_names_for_case(case_id or 0, "C")
        if not (out.get("respondents") or "").strip():
            out["respondents"] = _party_names_for_case(case_id or 0, "R")

        # “Filed by” — use latest KP-23 meta if missing
        if not (out.get("filed_by") or "").strip():
            fb = _latest_kp23_filer_name_for_case(case_id or 0)
            if fb: out["filed_by"] = fb

        # Date/Time Filed
        d_ans = (out.get("date_filed") or "").strip()
        d_obj = _try_parse_date(d_ans) or d_by_sub or _dt.now(ZoneInfo("Asia/Manila")).date()
        out["date_filed"] = _fmt_full(d_obj)

        t1 = (out.get("time_filed") or "").strip()
        t1_obj = _parse_time(t1) or t_by_sub
        out["time_filed"] = _fmt12(t1_obj) if t1_obj else ""

        # Per instruction: 2nd box should show complainants name
        out["time_filed_2"] = out.get("complaints", "") or out.get("time_filed_2", "")

        # ----- Motion date parts -----
        # Try to parse provided motion_date; else derive from filed date
        md_raw = (out.get("motion_date") or "").strip()
        md_obj = _try_parse_date(md_raw)
        if not md_obj:
            md_obj = d_obj

        # motion_date = day only; motion_month = UPPER month name; motion_year = year
        out["motion_date"]  = str(md_obj.day)
        out["motion_month"] = md_obj.strftime("%B").upper()
        out["motion_year"]  = str(md_obj.year)

        # motion_time 12h am/pm; fallback to time_filed
        mt_raw = (out.get("motion_time") or "").strip()
        mt_obj = _parse_time(mt_raw) or t1_obj
        out["motion_time"] = _fmt12(mt_obj) if mt_obj else ""

        # Duplicate name lines
        out.setdefault("complaints_two",  out.get("complaints",""))
        out.setdefault("respondents_two", out.get("respondents",""))

        # Signature names
        if not (out.get("complainants_sig") or "").strip():
            out["complainants_sig"] = _party_names_for_case(case_id or 0, "C")

        out.setdefault("respondents_sig",  out.get("respondents",""))

        # “This” fields (today)
        today = _dt.now(ZoneInfo("Asia/Manila")).date()
        out["this_date"] = str(today.day)
        out["this_year"] = str(today.year)

        # Chairman — default to PB; guard against accidental party-name values
        pb = get_lupon_chair_name(default="")
        ch = (out.get("chairman") or "").strip()
        parties = {
            out.get("complaints","").strip(),
            out.get("respondents","").strip(),
            out.get("filed_by","").strip()
        }
        if not ch or ch in parties or (pb and ch.lower() in pb.lower() and len(ch) < len(pb)):
            out["chairman"] = pb or ch

        # Sanitize & ensure all keys exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP24_FIELDS:
            out.setdefault(k, "")

        self._log(out)
        return out
