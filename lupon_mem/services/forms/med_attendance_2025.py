# lupon_mem/services/forms/med_attendance_2025.py
from __future__ import annotations
from typing import Dict, Set, Optional
import json, logging, re
from django.db import connection
from .. import form_shared as FS

logger = logging.getLogger(__name__)

_FIELDS = [
    "complainants","respondents","brgy_case_num","purpose",
    "person_one","person_two","person_three","person_four","person_five",
    "person_six","person_seven","person_eight","person_nine","person_ten",
    "pos_ten","pos_nine","pos_eight","pos_seven","pos_six","pos_five","pos_four","pos_three","pos_two","position_one",
    "respondents_2",
    "contact_three","contact_four","contact_five","contact_six","contact_seven","contact_eight","contact_nine","contact_ten",
    "contact_two","brgy_sec","brgy_chairman",
    "med_att_date_time_filed","med_att_med_hearing_date_time",
    "number",
]

_SOURCES: Dict[str, Set[str]] = {k: {k} for k in _FIELDS}
_SOURCES.update({
    "complainants": {"complainants", "complainant_name"},
    "respondents":  {"respondents", "respondent_name"},
    "respondents_2": {"respondents_2", "contact_one"},
})

# ---- Position normalization keys/logic
_POS_KEYS = ["position_one","pos_two","pos_three","pos_four","pos_five",
             "pos_six","pos_seven","pos_eight","pos_nine","pos_ten"]

_BRGY_LUPON_RE = re.compile(r"\b(?:brgy\.?|barangay)\s+lupon\s+member\b", re.IGNORECASE)
_BRGY_SEC_RE   = re.compile(r"\b(?:brgy\.?|barangay)\s+secretary\b", re.IGNORECASE)
_BRGY_CAP_RE   = re.compile(r"\b(?:brgy\.?|barangay)\s+captain\b", re.IGNORECASE)

def _canon_position(text: str) -> str:
    if not text:
        return text
    s = text.strip()
    if _BRGY_LUPON_RE.search(s):
        return "Lupon Member"
    if _BRGY_SEC_RE.search(s):
        return "Secretary"
    if _BRGY_CAP_RE.search(s):
        return "Captain"
    return s

def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s).strip()

def _name_from_person(first: str, middle: str, last: str, suffix: str) -> str:
    parts = [first or "", middle or "", last or "", suffix or ""]
    return _collapse_spaces(" ".join([p for p in parts if p]))

def _get_official_by_role(role_id: int) -> Optional[dict]:
    """
    Fetch Captain (role_id=3) or Secretary (role_id=4) from staff -> person.
    Returns {'name': str, 'mobile': str} or None.
    Schema used:
      staff.staff_id, staff.person_id, staff.role_id
      person.person_id, person.first_name, person.middle_name, person.last_name, person.suffix, person.mobile_num
    """
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.staff_id,
                    p.first_name, p.middle_name, p.last_name, p.suffix,
                    COALESCE(p.mobile_num, '') AS mobile_num
                FROM staff s
                JOIN person p ON p.person_id = s.person_id
                WHERE s.role_id = %s
                ORDER BY s.staff_id DESC
                LIMIT 1
                """,
                [role_id],
            )
            row = cur.fetchone()
        if not row:
            return None

        _, first, middle, last, suffix, mobile = row
        name = _name_from_person(first, middle, last, suffix)
        return {"name": FS.sanitize_text(name), "mobile": FS.sanitize_text(mobile or "")}
    except Exception as e:
        logger.warning("MED-ATT-2025: staff lookup failed for role_id=%s: %s", role_id, e)
        return None

class MedAttendance2025Handler:
    def _log(self, out: Dict[str,str]):
        try:
            print("[MED-ATT-2025] fill map:\n",
                  json.dumps({k: out.get(k, '') for k in _FIELDS},
                             ensure_ascii=False, indent=2))
        except Exception:
            pass

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers = FS.load_answers(submission_id)

        # fetch label/code map for this form
        with connection.cursor() as cur:
            cur.execute("""
                SELECT f.field_id,
                       LOWER(COALESCE(kff.label_override, f.base_label)),
                       LOWER(f.field_code)
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id = kff.field_id
                WHERE kff.form_id = %s
            """, [form_id])
            rows = cur.fetchall()

        by_label, by_code = {}, {}
        for fid, label, code in rows:
            val = answers.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = val
                if code:
                    by_code[code.strip().lower()] = val

        def get(keys: Set[str]) -> str:
            for k in keys:
                if k in by_label:
                    return FS.normalize(by_label[k])
                if k in by_code:
                    return FS.normalize(by_code[k])
            return ""

        out = {t: get(s) for t, s in _SOURCES.items()}

        # sanitize all strings
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)

        # ensure every known field key exists
        for k in _FIELDS:
            out.setdefault(k, "")

        # position normalization
        for k in _POS_KEYS:
            out[k] = _canon_position(out.get(k, ""))

        # ---- Auto-fill Barangay officials from staff table if blank ----
        try:
            # Captain -> brgy_chairman
            if not out.get("brgy_chairman"):
                cap = _get_official_by_role(3)  # role_id 3 = Captain
                if cap and cap.get("name"):
                    out["brgy_chairman"] = cap["name"]

            # Secretary -> brgy_sec
            if not out.get("brgy_sec"):
                sec = _get_official_by_role(4)  # role_id 4 = Secretary
                if sec and sec.get("name"):
                    out["brgy_sec"] = sec["name"]
        except Exception as e:
            logger.warning("MED-ATT-2025: autofill officials failed: %s", e)

        self._log(out)
        return out
