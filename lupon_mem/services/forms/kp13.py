# lupon_mem/services/forms/kp13.py
from __future__ import annotations
from typing import Dict, Set, Optional
from datetime import datetime as _dt, date as _date
import json
import logging

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS
from .util import get_lupon_chair_name  # Pangkat Chairman (Lupon Chair/President)

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
    "appearance_time",     # h:MM AM/PM
    "date_entered",        # day (1..31)
    "month_entered",       # month name
    "year_entered",        # 4-digit year
    "chairman",            # Pangkat Chairman (Lupon Chair)
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
    # Subpoena specifics
    "subpoena_to": {"subpoena_to", "addr_to", "recipient", "addressed to"},
    "subpoena_witness": {"subpoena_witness", "witness", "witness_name", "witnesses"},
    # Appearance schedule (split fields below if needed)
    "appearance_date": {"appearance_date", "hearing_date", "schedule_date", "appearance_day", "day_of"},
    "appearance_month": {"appearance_month", "hearing_month", "schedule_month"},
    "appearance_year": {"appearance_year", "hearing_year", "schedule_year", "current_year"},
    "appearance_time": {"appearance_time", "hearing_time", "schedule_time"},
    # Entered date (default to today if blank)
    "date_entered": {"date_entered", "date_today", "current_date", "this_date", "date_created"},
    "month_entered": {"month_entered", "current_month", "month_today", "month_created"},
    "year_entered": {"year_entered", "current_year", "year_created"},
    # Chairman — we prefer Pangkat/Lupon Chair; allow common variants
    "chairman": {
        "pangkat chairman", "lupon chair", "lupon chairman",
        "punong barangay", "brgy_capt"
    },
}

class KP13Handler:
    """
    KP-13: SUBPOENA LETTER

    Changes:
      • Chairman line now uses Pangkat Chairman (Lupon Chair/President).
      • appearance_time is coerced to 12-hour 'h:MM AM/PM' (Windows-safe).
    """

    @staticmethod
    def _try_parse_date(s: str) -> Optional[_date]:
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
    def _to_12h(tstr: str, now_dt: _dt) -> str:
        """
        Windows-safe 'h:MM AM/PM' formatter.
        Accepts 'HH:MM', 'HH:MM:SS', 'h:MM AM/PM', or digits 'HHMM'.
        Falls back to now_dt.
        """
        def _fmt12(h: int, m: int) -> str:
            ampm = "AM" if h < 12 else "PM"
            hh = h % 12
            if hh == 0:
                hh = 12
            return f"{hh}:{m:02d} {ampm}"

        if not tstr or not tstr.strip():
            return _fmt12(now_dt.hour, now_dt.minute)

        s = tstr.strip()

        # Already AM/PM?
        for fmt in ("%I:%M %p",):
            try:
                dt = _dt.strptime(s, fmt)
                return _fmt12(dt.hour, dt.minute)
            except Exception:
                pass

        # 24h formats
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                dt = _dt.strptime(s, fmt)
                return _fmt12(dt.hour, dt.minute)
            except Exception:
                continue

        # Plain digits 'HHMM'
        if s.isdigit() and len(s) == 4:
            h, m = int(s[:2]), int(s[2:])
            if 0 <= h < 24 and 0 <= m < 60:
                return _fmt12(h, m)

        # Fallback
        return _fmt12(now_dt.hour, now_dt.minute)

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP13_FIELDS}
            print("[KP13] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP13 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP13 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers
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

        # Seed direct mappings
        out: Dict[str, str] = {}
        for target, sources in _KP13_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Derive/normalize appearance split (day/month/year) ---
        appearance_day   = (out.get("appearance_date") or "").strip()
        appearance_month = (out.get("appearance_month") or "").strip()
        appearance_year  = (out.get("appearance_year") or "").strip()

        parsed = None
        if appearance_day:
            parsed = self._try_parse_date(appearance_day)

        if parsed:
            appearance_day   = str(parsed.day)
            appearance_month = parsed.strftime("%B")
            appearance_year  = str(parsed.year)

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
            maybe = self._try_parse_date(out["date_entered"])
            if maybe:
                out["date_entered"] = str(maybe.day)

        if not (out.get("month_entered") or "").strip():
            out["month_entered"] = today.strftime("%B")

        if not (out.get("year_entered") or "").strip():
            out["year_entered"] = str(today.year)

        # --- Time → 12h AM/PM (Windows-safe) ---
        out["appearance_time"] = self._to_12h(out.get("appearance_time", ""), now_ph)

        # --- Chairman → Pangkat Chairman (Lupon Chair/President) ---
        if not (out.get("chairman") or "").strip():
            out["chairman"] = get_lupon_chair_name(default=out.get("chairman", ""))

        # --- Final sanitize & ensure all fields exist ---
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP13_FIELDS:
            out.setdefault(k, "")

        # Log final map
        self._log_fill_map(out)
        return out
