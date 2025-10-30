# lupon_mem/services/forms/kp12.py
from __future__ import annotations
from typing import Dict, Set, Optional
from datetime import datetime as _dt
import json
import logging

from django.db import connection
from .. import form_shared as FS
from zoneinfo import ZoneInfo  # Asia/Manila TZ
from .util import get_lupon_chair_name  # Pangkat Chairman (Lupon Chair/President)

logger = logging.getLogger(__name__)

# Exact field names in kp_form_no_12_notice_of_hearing_conciliation_proceedings.pdf
_KP12_FIELDS = [
    "complainants_one",
    "repondents_one",      # (typo in PDF) — keep as-is
    "date_created",        # DAY number (e.g., "7")
    "month_created",       # Month name (e.g., "October")
    "time_created",        # "h:MM AM/PM"
    "current_date",        # DAY number
    "current_month",       # Month name
    "current_year",        # "2025"
    "brgy_captain",        # Field name in PDF; will contain Pangkat Chairman name
    "notified_date",       # DAY number
    "notified_month",      # Month name
    "complainants_two",
    "respondents_two",
    "notified_year",       # "2025"
]

# Accept both label text and field_code from the builder (robust to common variants)
_KP12_SOURCES: Dict[str, Set[str]] = {
    "complainants_one": {
        "complainants_one", "complainants", "complainant(s)", "complainants one",
    },
    "repondents_one": {
        "repondents_one", "respondents_one", "respondents", "respondent(s)", "respondents one",
    },
    "date_created":  {"date_created", "date created"},
    "month_created": {"month_created", "month created"},
    "time_created":  {"time_created", "time created", "time_filed", "time filed", "appearance_time"},
    "current_date":  {"current_date", "current date"},
    "current_month": {"current_month", "current month"},
    "current_year":  {"current_year", "current year"},
    # note: PDF label shows Pangkat Chairman; underlying field key is brgy_captain
    "brgy_captain": {"pangkat chairman", "lupon chair", "lupon chairman"},
    "notified_date":  {"notified_date", "date notified"},
    "notified_month": {"notified_month", "month notified"},
    "notified_year":  {"notified_year", "year notified"},
    "complainants_two": {"complainants_two", "complainants – alternate", "complainants - alternate"},
    "respondents_two":  {"respondents_two", "respondents – alternate", "respondents - alternate"},
}

class KP12Handler:
    """
    KP-12: NOTICE OF HEARING (CONCILIATION)

    Behavior:
      • DAY fields are numbers ("7", "11"); month names capitalized; years "YYYY".
      • Pangkat Chairman auto-filled from Lupon Chair/President (role name: BARANGAY LUPON PRESIDENT).
      • time_created coerced to 12-hour format with AM/PM (e.g., "5:04 PM") on all OS (no %-I).
    """

    @staticmethod
    def _try_parse_date(s: Optional[str]):
        if not s:
            return None
        txt = s.strip()
        if txt.isdigit():
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return _dt.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _to_12h(tstr: str, now_dt: _dt) -> str:
        """
        Return time in 12-hour 'h:MM AM/PM' without using %-I (works on Windows).
        Accepts: 'HH:MM', 'HH:MM:SS', or 'h:MM AM/PM'; falls back to now_dt.
        Also accepts 'HHMM' digits (e.g., '1704').
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
        try:
            dt = _dt.strptime(s, "%I:%M %p")
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
            ordered = {k: out.get(k, "") for k in _KP12_FIELDS}
            print("[KP12] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP12 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP12 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-12 form
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

        # Seed direct mappings from saved answers/prefill
        out: Dict[str, str] = {}
        for target, sources in _KP12_SOURCES.items():
            out[target] = _find_any(sources)

        # ---- Defaults / derivations ----
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        def _coerce_to_day_month_year(val_date: str, fallback_dt):
            """
            Returns (day_str, month_str, year_str) based on:
              • If val_date is parseable date (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY),
                use its components.
              • If val_date is a pure number, treat it as the day and use fallback month/year.
              • If empty/unparseable, use fallback_dt.
            """
            if val_date:
                txt = val_date.strip()
                if txt.isdigit():
                    d = int(txt)
                    return str(d), fallback_dt.strftime("%B"), str(fallback_dt.year)
                parsed = self._try_parse_date(txt)
                if parsed:
                    return str(parsed.day), parsed.strftime("%B"), str(parsed.year)
            return str(fallback_dt.day), fallback_dt.strftime("%B"), str(fallback_dt.year)

        # --- Created stamps ---
        day_c, month_c, year_c = _coerce_to_day_month_year(out.get("date_created", ""), today)
        out["date_created"] = day_c
        if not (out.get("month_created") or "").strip():
            out["month_created"] = month_c

        # --- Current stamps (TODAY) ---
        day_cur, month_cur, year_cur = _coerce_to_day_month_year(out.get("current_date", ""), today)
        out["current_date"] = day_cur
        if not (out.get("current_month") or "").strip():
            out["current_month"] = month_cur
        if not (out.get("current_year") or "").strip():
            out["current_year"] = year_cur

        # --- Notified stamps (defaults to TODAY if blank) ---
        day_n, month_n, year_n = _coerce_to_day_month_year(out.get("notified_date", ""), today)
        out["notified_date"] = day_n
        if not (out.get("notified_month") or "").strip():
            out["notified_month"] = month_n
        if not (out.get("notified_year") or "").strip():
            out["notified_year"] = year_n

        # Time → 12h AM/PM (Windows-safe)
        out["time_created"] = self._to_12h(out.get("time_created", ""), now_ph)

        # Pangkat Chairman (Lupon Chair/President)
        if not (out.get("brgy_captain") or "").strip():
            out["brgy_captain"] = get_lupon_chair_name(default=out.get("brgy_captain", ""))

        # Final sanitize & ensure all known fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP12_FIELDS:
            out.setdefault(k, "")

        # Log what's being filled into the PDF (ordered)
        self._log_fill_map(out)

        return out
