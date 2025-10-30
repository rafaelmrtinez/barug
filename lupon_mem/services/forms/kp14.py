# lupon_mem/services/forms/kp14.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt, date as _date
import json
import logging

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Exact field names in kp_form_no_14_agreement_for_arbitration.pdf
_KP14_FIELDS = [
    "complainants",
    "respondents",
    "brgy_case_number",
    "purpose",
    "date_entered",       # day (1..31)
    "month_entered",      # month name (January..December)
    "year_entered",       # 4-digit year
    "complainants_two",   # mirror of complainants
    "respondents_two",    # mirror of respondents
    "chairman",           # Punong Barangay / Chairman
]

# Accept both label text and field_code from the builder (robust to common variants)
_KP14_SOURCES: Dict[str, Set[str]] = {
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
    # Entered date trio (default: TODAY if blank)
    "date_entered": {"date_entered", "date_today", "current_date", "this_date", "date_created"},
    "month_entered": {"month_entered", "current_month", "month_today", "month_created"},
    "year_entered": {"year_entered", "current_year", "year_created"},
    # Chairman (Punong Barangay)
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
    # Optional explicit mirrors (if present, we’ll take them; otherwise we’ll mirror below)
    "complainants_two": {"complainants_two", "complainants - alternate", "complainants – alternate"},
    "respondents_two": {"respondents_two", "respondents - alternate", "respondents – alternate"},
}

class KP14Handler:
    """
    KP-14: AGREEMENT FOR ARBITRATION

    Behavior:
      • Pull values from saved answers by label or field_code.
      • Default entered date (date_entered/month_entered/year_entered) to TODAY (Asia/Manila), if blank.
      • Mirror complainants_two/respondents_two from the main lists if not explicitly provided.
      • Sanitize/normalize all strings and ensure all target PDF fields exist.
      • Log the final ordered map that’s filled into the PDF.
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
        try:
            ordered = {k: out.get(k, "") for k in _KP14_FIELDS}
            print("[KP14] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP14 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP14 logging failed: %s", e)

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-14 form
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
        for target, sources in _KP14_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Defaults for “entered” date trio = TODAY (Asia/Manila) ---
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        # date_entered should be the DAY number only
        de_raw = (out.get("date_entered") or "").strip()
        if not de_raw:
            out["date_entered"] = str(today.day)
        else:
            maybe = self._try_parse_date(de_raw)
            out["date_entered"] = str(maybe.day) if maybe else FS.normalize(de_raw)

        if not (out.get("month_entered") or "").strip():
            out["month_entered"] = today.strftime("%B")

        if not (out.get("year_entered") or "").strip():
            out["year_entered"] = str(today.year)

        # --- Mirror alternates if blank ---
        if not (out.get("complainants_two") or "").strip():
            out["complainants_two"] = out.get("complainants", "")
        if not (out.get("respondents_two") or "").strip():
            out["respondents_two"] = out.get("respondents", "")

        # --- Final sanitize & ensure all fields exist ---
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP14_FIELDS:
            out.setdefault(k, "")

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
