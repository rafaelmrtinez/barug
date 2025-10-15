# kp10.py
from __future__ import annotations
from typing import Dict, Set
from datetime import date as _date, datetime as _dt

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
    "appear_to",          # will hold DAY (1..31)
    "appearance_date",    # will hold MONTH NAME (January..December)
    "current_year",       # will hold YYYY
    "appearance_time",
    "date_today",         # must be MONTH NAME (e.g., "October")
    "day_of",
    "date_notified",      # must be MONTH NAME (e.g., "October")
    "notified_day_of",
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

    New behavior for the single picked date:
      • appear_to          = DAY (e.g., 13)
      • appearance_date    = MONTH NAME (e.g., January)
      • current_year       = 4-digit YEAR (e.g., 2026)

    We look for the date value from either:
      • field_code 'appearance_date' (your “Hearing Details” date input)
      • OR (fallback) a value saved under label 'hearing details' / 'hearing date'.
    """

    @staticmethod
    def _try_parse_date(s: str):
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
        Log the final field → value map in the exact order of _KP10_FIELDS.
        Shows in console during dev; goes to your configured logs in prod.
        """
        try:
            ordered = {k: out.get(k, "") for k in _KP10_FIELDS}
            # always visible in runserver console
            print("[KP10] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            # also log (shows if logger level is INFO)
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

        # ------- Derive from the single picked date -------
        # Primary source is the field with code 'appearance_date' (Hearing Details),
        # but accept label fallbacks too.
        picked_date_txt = (
            by_code.get("appearance_date")
            or by_label.get("hearing details")
            or by_label.get("hearing date")
            or ""
        )
        d = self._try_parse_date(picked_date_txt)

        if d:
            # appear_to = DAY number
            out["appear_to"] = str(d.day)

            # appearance_date = MONTH NAME
            out["appearance_date"] = d.strftime("%B")

            # current_year = 4-digit year
            out["current_year"] = str(d.year)

        # Mirrors for alternates
        if not (out.get("complainants_2") or "").strip():
            out["complainants_2"] = out.get("complainants", "")
        if not (out.get("respondents_2") or "").strip():
            out["respondents_2"] = out.get("respondents", "")

        # ------- Philippine time anchor (Asia/Manila) -------
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        # --- date_today → MONTH NAME (normalize if it came as a date) ---
        raw_dt_today = (out.get("date_today") or "").strip()
        if raw_dt_today:
            parsed_today = self._try_parse_date(raw_dt_today)
            if parsed_today:
                out["date_today"] = parsed_today.strftime("%B")
            else:
                # if already a month name, keep as-is
                out["date_today"] = raw_dt_today
        else:
            out["date_today"] = today.strftime("%B")

        # --- years (keep your mirrors) ---
        for ykey in ("current_year", "current_year_2", "current_year_3"):
            if not (out.get(ykey) or "").strip():
                out[ykey] = str(today.year)

        # --- day_of (from picked date d; else from date_today/today) ---
        if d:
            out["day_of"] = str(d.day)
        else:
            if not (out.get("day_of") or "").strip():
                # date_today is just a month name, so parsing won't produce a full date; fallback to today's day
                td = self._try_parse_date(out.get("date_today", ""))
                out["day_of"] = str(td.day) if td else str(today.day)

        # --- date_notified → MONTH NAME and notified_day_of → DAY ---
        raw_notified = (out.get("date_notified") or "").strip()
        nd = self._try_parse_date(raw_notified)
        if nd:
            out["notified_day_of"] = str(nd.day)      # e.g., "11"
            out["date_notified"] = nd.strftime("%B")  # e.g., "October"
        elif raw_notified:
            # if already a month name, keep as-is; otherwise leave untouched
            out["date_notified"] = raw_notified

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP10_FIELDS:
            out.setdefault(k, "")

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
