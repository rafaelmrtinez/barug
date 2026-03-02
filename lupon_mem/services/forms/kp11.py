# kp11.py
from __future__ import annotations
from typing import Dict, Set
from datetime import date as _date, datetime as _dt

import json
import logging

from django.db import connection
from .. import form_shared as FS
from zoneinfo import ZoneInfo  # PH time
from .util import get_captain_name, get_secretary_name  # util helpers

logger = logging.getLogger(__name__)

# Exact field names in kp_form_no_11_notice_to_chosen_pangkat_member.pdf
_KP11_FIELDS = [
    "complainants",
    "repondents",          # (typo in PDF) — we will still fill this
    "brgy_case_num",
    "purpose",
    "date_today",          # ← will be "October 20, 2025"
    "recepient",           # (typo in PDF) — we will still fill this
    "brgy_capt",
    "rcvd_date",           # day (1..31)
    "rcvd_month",          # month name (January..December)
    "pangkat_member_name",
    "rcvd_month_2",        # we use this for YEAR (e.g., 2025)
]

# Accept both label text and field_code from the builder (robust to common variants)
_KP11_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants": {"complainants", "complainant(s)"},
    # PDF field is misspelled as "repondents"
    "repondents": {"repondents", "respondents", "respondent(s)"},
    # Case No.
    "brgy_case_num": {
        "brgy_case_num", "barangay case no.", "brgy case no.", "brgy case number",
        "case no.", "case number", "case_num"
    },
    # Purpose/For
    "purpose": {"purpose", "for"},
    # Today
    "date_today": {"date_today", "current_date", "this_date", "date", "date_created"},
    # Recipient (PDF typo: recepient)
    "recepient": {"pangkat_member_name", "pangkat member name", "pangkat_member"},
    # Barangay Captain
    "brgy_capt": {"brgy_capt", "punong barangay", "barangay captain", "chairman", "brgy capt"},
    # Received day/month (explicit if the form supplies them)
    "rcvd_date": {"rcvd_date", "received_day", "day_received"},
    "rcvd_month": {"rcvd_month", "received_month", "month_received"},
    # Pangkat member name
    "pangkat_member_name": {"pangkat_member_name", "pangkat member name", "pangkat_member"},
    # Second month mirror (PDF label says month, but your layout wants YEAR here)
    "rcvd_month_2": {"rcvd_month_2"},
}

class KP11Handler:
    """
    KP-11: NOTICE TO CHOSEN PANGKAT MEMBER

    Behavior:
      • Pull values from saved answers by label or field_code.
      • date_today is rendered as "Month DD, YYYY" (e.g., "October 20, 2025").
      • If rcvd_date / rcvd_month are blank, derive them from date_today:
            rcvd_date  = day number (1..31)
            rcvd_month = month name (January..December)
        And rcvd_month_2 = YEAR (e.g., "2025") for your PDF.
      • Auto-fill Barangay Captain if blank using staff table.
      • Print/log the final ordered map.
    """

    @staticmethod
    def _try_parse_date(s: str):
        if not s:
            return None
        txt = s.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y"):
            try:
                return _dt.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _to_long_date(d: _date) -> str:
        # Cross-platform "October 20, 2025" (no %-d, no leading zero issues)
        return f"{d.strftime('%B')} {d.day}, {d.year}"

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP11_FIELDS}
            print("[KP11] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP11 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP11 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-11 form
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
        for target, sources in _KP11_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Defaults / derivations ---
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        # Parse incoming date_today (may be blank or ISO). Always render as "Month DD, YYYY".
        parsed = self._try_parse_date(out.get("date_today", "")) or today
        out["date_today"] = self._to_long_date(parsed)

        # Parse rcvd_date if it's a full date string, extract day/month/year
        rcvd_parsed = self._try_parse_date(out.get("rcvd_date", "")) or parsed
        out["rcvd_date"] = str(rcvd_parsed.day)
        out["rcvd_month"] = rcvd_parsed.strftime("%B").upper()
        out["rcvd_month_2"] = str(rcvd_parsed.year)

        # --- Auto-fill officials if missing ---
        if not (out.get("brgy_capt") or "").strip():
            out["brgy_capt"] = get_captain_name(default=out.get("brgy_capt", "")) or out.get("brgy_capt", "")

        # (KP-11 usually doesn't print the Secretary, but util is available)
        # Example if you add a field later:
        # if not (out.get("brgy_sec") or "").strip():
        #     out["brgy_sec"] = get_secretary_name()

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP11_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-11 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp11_mediation_proceedings
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [submission_id]
                )
                row = cur.fetchone()
                if row:
                    case_id = row[0]
                    case_num = out.get("brgy_case_num", "")
                    if not case_num:
                        cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                        case_row = cur.fetchone()
                        case_num = case_row[0] if case_row else ""
                    notify_kp11_mediation_proceedings(case_id, case_num)
        except Exception as e:
            logger.warning("[KP11] Failed to send notifications: %s", e)

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
