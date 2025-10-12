# lupon_mem/services/forms/kp13.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt, date as _date

import json
import logging

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Exact field names in kp_form_no_13_subpoena_letter.pdf
_KP13_FIELDS = [
    "complainants",
    "respondents",
    "brgy_case_number",
    "purpose",
    "subpoena_to",
    "subpoena_witness",
    "appearance_date",     # day (1..31)
    "appearance_month",    # month name (January..December)
    "appearance_year",     # 4-digit year
    "appearance_time",     # hh:mm (as entered)
    "date_entered",        # day (1..31)
    "month_entered",       # month name
    "year_entered",        # 4-digit year
    "chairman",            # Punong Barangay / Chairman
]

# Accept both label text and field_code from the builder (robust to common variants)
_KP13_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants": {"complainants", "complainant(s)"},
    "respondents": {"respondents", "respondent(s)"},
    # Case No.
    "brgy_case_number": {
        "brgy_case_number", "brgy_case_num", "brgy case number", "brgy case no.",
        "barangay case no.", "case number", "case no.", "case_num"
    },
    # Purpose (a.k.a. “For”)
    "purpose": {"purpose", "for"},
    # Subpoena specific
    "subpoena_to": {"subpoena_to", "addr_to", "recipient", "addressed to"},
    "subpoena_witness": {"subpoena_witness", "witness", "witness_name", "witnesses"},
    # Appearance schedule (we’ll derive split fields below)
    "appearance_date": {"appearance_date", "hearing_date", "schedule_date", "appearance_day", "day_of"},
    "appearance_month": {"appearance_month", "hearing_month", "schedule_month"},
    "appearance_year": {"appearance_year", "hearing_year", "schedule_year", "current_year"},
    "appearance_time": {"appearance_time", "hearing_time", "schedule_time"},
    # Entered date (we’ll default to today if blank)
    "date_entered": {"date_entered", "date_today", "current_date", "this_date", "date_created"},
    "month_entered": {"month_entered", "current_month", "month_today", "month_created"},
    "year_entered": {"year_entered", "current_year", "year_created"},
    # Chairman (Punong Barangay)
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
}

class KP13Handler:
    """
    KP-13: SUBPOENA LETTER

    Behavior:
      • Pull values from saved answers by label or field_code.
      • Derive the split appearance_date/month/year from any provided date-like source:
            - If appearance_date is an ISO-like date (YYYY-MM-DD), split into D/M/Y.
            - If only month/year provided, keep as-is and leave what’s missing blank.
      • Default entered date (date_entered/month_entered/year_entered) to TODAY (Asia/Manila), if blank.
      • Sanitize/normalize all strings and ensure all target PDF fields exist.
      • Print & log (INFO) the final ordered map that’s filled into the PDF.
    """

    @staticmethod
    def _try_parse_date(s: str) -> _date | None:
        if not s:
            return None
        txt = s.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return _dt.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        """
        Log/print the final field → value map in the exact order of _KP13_FIELDS.
        """
        try:
            ordered = {k: out.get(k, "") for k in _KP13_FIELDS}
            # always visible in runserver console
            print("[KP13] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            # also log (shows if logger level is INFO)
            logger.info("KP13 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP13 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-13 form
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
        for target, sources in _KP13_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Derive/normalize appearance split (day/month/year) ---
        # If appearance_date looks like a full date, split it. Otherwise,
        # keep what’s given and fill blanks if there are alternatives.
        # Priority order:
        #   1) Parse out['appearance_date'] if it’s a full date string
        #   2) Else, try any of date_entered/current_date (not ideal, but a fallback)
        appearance_day   = (out.get("appearance_date") or "").strip()
        appearance_month = (out.get("appearance_month") or "").strip()
        appearance_year  = (out.get("appearance_year") or "").strip()

        # Try strict parse from a date-like string in any of those
        parsed = None
        if appearance_day:
            parsed = self._try_parse_date(appearance_day)
        if not parsed and out.get("date_entered"):
            parsed = self._try_parse_date(out.get("date_entered", ""))

        if parsed:
            # Use parsed date to set/override the trio
            appearance_day   = str(parsed.day)
            appearance_month = parsed.strftime("%B")
            appearance_year  = str(parsed.year)

        # Ensure trio is set back
        if appearance_day:
            out["appearance_date"] = appearance_day
        if appearance_month:
            out["appearance_month"] = appearance_month
        if appearance_year:
            out["appearance_year"] = appearance_year

        # --- Defaults for “entered” date trio = TODAY (Asia/Manila) ---
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        if not (out.get("date_entered") or "").strip():
            out["date_entered"] = str(today.day)
        else:
            # If a full date slipped here, normalize to just day number
            maybe = self._try_parse_date(out["date_entered"])
            if maybe:
                out["date_entered"] = str(maybe.day)

        if not (out.get("month_entered") or "").strip():
            out["month_entered"] = today.strftime("%B")

        if not (out.get("year_entered") or "").strip():
            out["year_entered"] = str(today.year)

        # --- Final sanitize & ensure all fields exist ---
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP13_FIELDS:
            out.setdefault(k, "")

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
