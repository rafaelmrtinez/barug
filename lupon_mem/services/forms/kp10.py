# kp10.py
from __future__ import annotations
from typing import Dict, Set, Optional
from datetime import date as _date, datetime as _dt, time as _time

import json
import logging

from django.db import connection
from django.conf import settings
from .. import form_shared as FS
from zoneinfo import ZoneInfo  # Asia/Manila timezone

logger = logging.getLogger(__name__)

_KP10_FIELDS = [
    "addr_to",
    "complainants",
    "respondents",
    "appear_to",          # DAY (1..31) of the hearing
    "appearance_date",    # MONTH NAME of the hearing
    "current_year",       # YYYY of the hearing
    "appearance_time",    # 12h with AM/PM
    "date_today",         # MONTH NAME (current date)
    "day_of",             # DAY (current date)
    "date_notified",      # MONTH NAME (default: current)
    "notified_day_of",    # DAY (default: current)
    "complainants_2",
    "respondents_2",
    "current_year_2",
    "current_year_3",
]

# Accept both label text and field_code from the builder
_KP10_SOURCES: Dict[str, Set[str]] = {
    # parties / addressed to
    "addr_to": {"addr_to", "addressed to"},
    "complainants": {"complainants", "complainant(s)"},
    "respondents": {"respondents", "respondent(s)"},
    "complainants_2": {"complainants_2", "complainant(s) – alternate", "complainant(s) - alternate"},
    "respondents_2": {"respondents_2", "respondent(s) – alternate", "respondent(s) - alternate"},

    # schedule/time straight maps (date will be derived below)
    "appearance_time": {"appearance_time", "notice_time", "time_filed", "time_created"},

    # today / year mirrors
    "date_today": {"date_today", "date_created", "current_date", "this_date", "date"},
    "current_year_2": {"current_year_2", "this_year", "year_created", "year_received", "year"},
    "current_year_3": {"current_year_3", "this_year", "year_created", "year_received", "year"},

    # notified
    "date_notified": {"date_notified"},
    "day_of": {"day_of"},
    "notified_day_of": {"notified_day_of"},
}


class KP10Handler:
    """
    KP-10: NOTICE FOR CONSTITUTION OF PANGKAT

    Single picked hearing date provides:
      • appear_to          = DAY (e.g., 13)
      • appearance_date    = MONTH NAME (e.g., January)
      • current_year       = 4-digit YEAR (e.g., 2026)

    “This ___ day of ___” (date_today + day_of) must always reflect the **current date**
    in Asia/Manila, not the picked hearing date.

    appearance_time is normalized to **12-hour AM/PM**.
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
    def _try_parse_time(s: str) -> Optional[_time]:
        """
        Accepts common time formats, returns a time object if possible.
        """
        if not s:
            return None
        txt = s.strip().upper().replace(".", "")
        # Try 24h first
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return _dt.strptime(txt, fmt).time()
            except Exception:
                pass
        # Then 12h variants
        for fmt in ("%I:%M %p", "%I:%M%p", "%I %p"):
            try:
                return _dt.strptime(txt, fmt).time()
            except Exception:
                pass
        return None

    @staticmethod
    def _format_12h(t: _time) -> str:
        """
        Formats to 'HH:MM AM/PM' (no leading space). Ensures 12-hour clock with AM/PM.
        """
        return _dt.combine(_dt.today(), t).strftime("%I:%M %p").lstrip("0")

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        """
        Log the final field → value map in the exact order of _KP10_FIELDS.
        Shows in console during dev; goes to your configured logs in prod.
        """
        try:
            ordered = {k: out.get(k, "") for k in _KP10_FIELDS}
            print("[KP10] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP10 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP10 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

        # discover label/code + pull saved answers
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
        for target, sources in _KP10_SOURCES.items():
            out[target] = _find_any(sources)

        # ------- Derive from the single picked hearing date (for appear_to / appearance_date / current_year) -------
        picked_date_txt = (
            by_code.get("appearance_date")
            or by_label.get("hearing details")
            or by_label.get("hearing date")
            or ""
        )
        d = self._try_parse_date(picked_date_txt)

        if d:
            # appear_to = DAY number of hearing
            out["appear_to"] = str(d.day)
            # appearance_date = MONTH NAME of hearing
            out["appearance_date"] = d.strftime("%B")
            # current_year = 4-digit hearing year
            out["current_year"] = str(d.year)

        # Mirrors for alternates
        if not (out.get("complainants_2") or "").strip():
            out["complainants_2"] = out.get("complainants", "")
        if not (out.get("respondents_2") or "").strip():
            out["respondents_2"] = out.get("respondents", "")

        # ------- Philippine time anchor (Asia/Manila) -------
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        # === “This ___ day of ___” must be TODAY (current date) ===
        # month
        out["date_today"] = today.strftime("%B")
        # day
        out["day_of"] = str(today.day)
        # fallback years
        for ykey in ("current_year", "current_year_2", "current_year_3"):
            if not (out.get(ykey) or "").strip():
                out[ykey] = str(today.year)

        # --- date_notified / notified_day_of: if not provided or unparseable, default to TODAY ---
        raw_notified = (out.get("date_notified") or "").strip()
        nd = self._try_parse_date(raw_notified)
        if nd:
            out["notified_day_of"] = str(nd.day)
            out["date_notified"] = nd.strftime("%B")
        else:
            # default to today if missing or not a date/month
            if not raw_notified:
                out["date_notified"] = today.strftime("%B")
            if not (out.get("notified_day_of") or "").strip():
                out["notified_day_of"] = str(today.day)

        # --- appearance_time: normalize to 12h with AM/PM (fallback to now) ---
        raw_time = (out.get("appearance_time") or "").strip()
        parsed_time = self._try_parse_time(raw_time)
        if not parsed_time:
            parsed_time = now_ph.time().replace(second=0, microsecond=0)
        out["appearance_time"] = self._format_12h(parsed_time)

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP10_FIELDS:
            out.setdefault(k, "")

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
