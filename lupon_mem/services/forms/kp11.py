# kp11.py
from __future__ import annotations
from typing import Dict, Set
from datetime import date as _date, datetime as _dt

import json
import logging

from django.db import connection
from .. import form_shared as FS
from zoneinfo import ZoneInfo  # PH time

logger = logging.getLogger(__name__)

# Exact field names in kp_form_no_11_notice_to_chosen_pangkat_member.pdf
_KP11_FIELDS = [
    "complainants",
    "repondents",          # (typo in PDF) — we will still fill this
    "brgy_case_num",
    "purpose",
    "date_today",
    "recepient",           # (typo in PDF) — we will still fill this
    "brgy_capt",
    "rcvd_date",           # day (1..31)
    "rcvd_month",          # month name (January..December)
    "pangkat_member_name",
    "rcvd_month_2",        # in practice: YEAR (per user’s PDF)
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
    "recepient": {"recepient", "recipient", "addr_to", "addressed to"},
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
      • Default date_today = today (YYYY-MM-DD, Asia/Manila) if blank.
      • If rcvd_date / rcvd_month are blank, derive them from date_today:
            rcvd_date  = day number (1..31)
            rcvd_month = month name (January..December)
      • rcvd_month_2 = YEAR (e.g., "2025") — per your PDF usage.
      • Keep builder/prefill-resolved party names, case no., purpose, captain, recipient, etc.
      • Print & log (INFO) the final ordered map that’s filled into the PDF.
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
        Log/print the final field → value map in the exact order of _KP11_FIELDS.
        """
        try:
            ordered = {k: out.get(k, "") for k in _KP11_FIELDS}
            # always visible in runserver console
            print("[KP11] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            # also log (shows if logger level is INFO)
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
        # Ensure date_today using Asia/Manila
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()
        if not (out.get("date_today") or "").strip():
            out["date_today"] = today.isoformat()

        # Derive rcvd_date / rcvd_month / rcvd_month_2(YEAR) from date_today if blank
        dt = self._try_parse_date(out.get("date_today", "")) or today
        if not (out.get("rcvd_date") or "").strip():
            out["rcvd_date"] = str(dt.day)
        if not (out.get("rcvd_month") or "").strip():
            out["rcvd_month"] = dt.strftime("%B")

        # IMPORTANT: your layout wants YEAR in rcvd_month_2
        if not (out.get("rcvd_month_2") or "").strip():
            out["rcvd_month_2"] = str(dt.year)

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP11_FIELDS:
            out.setdefault(k, "")

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
