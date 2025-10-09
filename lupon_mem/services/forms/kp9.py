# kp9.py
from __future__ import annotations
from typing import Dict, Set
from datetime import date as _date, datetime as _dt
from .. import form_shared as FS
from django.db import connection  # used like in KP-7 to fetch label/code mapping

# Exact AcroForm field names in kp_form_no_9_summon_for_the_respondent.pdf
_KP9_FIELDS = [
    "complainants","respondents","brgy_case_number","purpose","recipient",
    "summon_date","summon_month","summon_year","summon_time",
    "curr_date","curr_month","curr_year","brgy_capt",
    "served_to","date_offcret","month_offcret","ofcret_year",
    "respondent_offcr_ret","offcret_serve_date","offcret_serve_month","offcret_serve_year",
    "respondent_names_one","respondent_names_two","respondent_names_three",
    "proxy_name_one","served_to_2","proxy_name_two","offcr_name",
    "served_to_3","date_signed_one","date_signed_two","served_to_4",
]

# Optional synonyms (accept either field label or field_code from the builder)
_KP9_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants", "complainant(s)"},
    "respondents": {"respondents", "respondent(s)"},
    "brgy_case_number": {"brgy_case_number", "brgy_case_num", "case_num", "barangay case no."},
    "purpose": {"purpose", "for"},
    "recipient": {"recipient"},
    "summon_date": {"summon_date"},
    "summon_month": {"summon_month"},
    "summon_year": {"summon_year"},
    "summon_time": {"summon_time"},
    "curr_date": {"curr_date"},
    "curr_month": {"curr_month"},
    "curr_year": {"curr_year"},
    "brgy_capt": {"brgy_capt", "brgy_captain", "chairman", "punong_barangay"},
    "served_to": {"served_to"},
    "date_offcret": {"date_offcret"},
    "month_offcret": {"month_offcret"},
    "ofcret_year": {"ofcret_year"},
    "respondent_offcr_ret": {"respondent_offcr_ret"},
    "offcret_serve_date": {"offcret_serve_date"},
    "offcret_serve_month": {"offcret_serve_month"},
    "offcret_serve_year": {"offcret_serve_year"},
    "respondent_names_one": {"respondent_names_one"},
    "respondent_names_two": {"respondent_names_two"},
    "respondent_names_three": {"respondent_names_three"},
    "proxy_name_one": {"proxy_name_one"},
    "served_to_2": {"served_to_2"},
    "proxy_name_two": {"proxy_name_two"},
    "offcr_name": {"offcr_name"},
    "served_to_3": {"served_to_3"},
    "date_signed_one": {"date_signed_one"},
    "date_signed_two": {"date_signed_two"},
    "served_to_4": {"served_to_4"},
}

_DEFAULT_PUNONG_BARANGAY = "Lourdes Ramirez"


class KP9Handler:
    """
    KP-9: Summon for the Respondent
    """

    def _fetch_punong_barangay_from_db(self) -> str:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT trim(
                        coalesce(p.first_name,'') || ' ' ||
                        coalesce(p.middle_name,'') || ' ' ||
                        coalesce(p.last_name,'')  || ' ' ||
                        coalesce(p.suffix,'')
                    ) AS name
                    FROM staff s
                    JOIN person p ON p.person_id = s.person_id
                    JOIN rolee  r ON r.role_id   = s.role_id
                    WHERE r.role_name = 'BARANGAY CAPTAIN'
                    ORDER BY s.staff_id DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row and (row[0] or "").strip():
                    return row[0].strip()
        except Exception:
            pass
        return _DEFAULT_PUNONG_BARANGAY

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _try_parse_date(s: str):
        """Return a datetime.date from common inputs, else None."""
        if not s:
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_triplet(out: Dict[str, str], day_key: str, mon_key: str, yr_key: str):
        """
        If out[day_key] looks like a date string, convert:
          day_key -> day-of-month (e.g., '9')
          mon_key -> 'October'
          yr_key  -> '2025'
        Leaves existing month/year if already present.
        """
        raw = (out.get(day_key) or "").strip()
        dt = KP9Handler._try_parse_date(raw)
        if dt:
            out[day_key] = str(dt.day)  # day-of-month only
            if not (out.get(mon_key) or "").strip():
                out[mon_key] = dt.strftime("%B")
            if not (out.get(yr_key) or "").strip():
                out[yr_key] = str(dt.year)

    # ------------------------------------------------------------------------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

        # Fetch labels/codes available on this form
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT f.field_id,
                       LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                       LOWER(f.field_code)
                FROM kp_form_field kff
                JOIN kp_field f ON f.field_id = kff.field_id
                WHERE kff.form_id=%s
                """,
                [form_id],
            )
            rows = cur.fetchall()

        by_label, by_code = {}, {}
        for fid, label, field_code in rows:
            val = answers_by_id.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = val
                if field_code:
                    by_code[field_code.strip().lower()] = val

        def _find_any(keys: Set[str]) -> str:
            for k in keys:
                kk = k.strip().lower()
                if kk in by_label:
                    return FS.normalize(by_label[kk])
                if kk in by_code:
                    return FS.normalize(by_code[kk])
            return ""

        out: Dict[str, str] = {}
        for target, sources in _KP9_SOURCES.items():
            out[target] = _find_any(sources)

        # Convenience: replicate respondents lines & default recipient
        respondents_val = (out.get("respondents") or "").strip()
        if respondents_val:
            out.setdefault("respondent_names_one", respondents_val)
            out.setdefault("respondent_names_two", respondents_val)
            out.setdefault("respondent_names_three", respondents_val)
            if not (out.get("recipient") or "").strip():
                out["recipient"] = respondents_val.split(",")[0].strip()

        # Today's stamps if missing
        today = _date.today()
        out.setdefault("curr_date", today.isoformat())
        out.setdefault("curr_month", today.strftime("%B"))
        out.setdefault("curr_year", str(today.year))

        # Ensure brgy_capt mirrors PB
        pb_from_inputs = ""
        for key in ("punong barangay", "punong_barangay", "brgy_captain", "chairman"):
            v = _find_any({key})
            if v:
                pb_from_inputs = v
                break
        pb_name = pb_from_inputs or self._fetch_punong_barangay_from_db()
        if not (out.get("brgy_capt") or "").strip():
            out["brgy_capt"] = pb_name

        # --- NEW: normalize date triplets so PDF shows correct "day of" values ----
        # Summons triplet
        self._normalize_triplet(out, "summon_date", "summon_month", "summon_year")
        # Current date triplet (signature line on page 1)
        self._normalize_triplet(out, "curr_date", "curr_month", "curr_year")
        # Officer Served triplet
        self._normalize_triplet(out, "offcret_serve_date", "offcret_serve_month", "offcret_serve_year")
        # Officer's Return triplet; if blank, derive from offcret_serve_date
        if not (out.get("date_offcret") or "").strip():
            out["date_offcret"] = out.get("offcret_serve_date", "")
        if not (out.get("month_offcret") or "").strip():
            out["month_offcret"] = out.get("offcret_serve_month", "")
        if not (out.get("ofcret_year") or "").strip():
            out["ofcret_year"] = out.get("offcret_serve_year", "")
        self._normalize_triplet(out, "date_offcret", "month_offcret", "ofcret_year")

        # Final sanitize and ensure all fields present
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP9_FIELDS:
            out.setdefault(k, "")

        return out
