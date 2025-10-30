# lupon_mem/services/forms/kp15.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime as _dt, date as _date

import json
import logging

from django.db import connection
from zoneinfo import ZoneInfo  # PH time
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Role IDs (per your seeds; secretary is 4)
SECRETARY_ROLE_ID = 4

# Exact PDF field names in kp_form_no_15_arbitration_award.pdf
_KP15_FIELDS = [
    "complainants",
    "respondents",
    "brgy_case_num",
    "purpose",
    "award_description",
    "date_made",     # day (1..31)
    "month_made",    # full month name
    "year_made",     # 4-digit year
    "chairman",
    "member",
    "member_two",
    "secretary",
]

# Accept both label text and field_code variants from the builder
_KP15_SOURCES: Dict[str, Set[str]] = {
    # Parties
    "complainants": {"complainants", "complainant(s)", "party-complainants", "parties_complainants"},
    "respondents":  {"respondents", "respondent(s)", "party-respondents", "parties_respondents"},

    # Case number
    "brgy_case_num": {
        "brgy_case_num", "brgy_case_number", "brgy case no.", "brgy case number",
        "barangay case no.", "case number", "case no.", "case_num"
    },

    # Purpose (often “For”)
    "purpose": {"purpose", "for", "case_purpose"},

    # Award description / terms of award
    "award_description": {
        "award_description", "arbitration_award", "award_details", "details_of_award",
        "agreement_terms", "terms_of_award", "settlement_terms", "narrative", "description"
    },

    # Date split: day / month / year the award was made
    "date_made":  {"date_made", "date_awarded", "date_of_award", "date_created", "date_today"},
    "month_made": {"month_made", "award_month", "current_month", "month_today"},
    "year_made":  {"year_made", "award_year", "current_year", "year_today"},

    # Signatories
    "chairman": {"chairman", "punong barangay", "barangay captain", "brgy_capt", "brgy captain"},
    "member": {"member", "pangkat_member", "pangkat member", "pangkat_member_1", "pangkat_member_one", "lupon_member"},
    "member_two": {"member_two", "member 2", "pangkat_member_2", "pangkat_member_two", "lupon_member_2"},
    "secretary": {"secretary", "barangay secretary", "lupon secretary", "lupon_secretary"},
}


class KP15Handler:
    """
    KP-15: ARBITRATION AWARD

    Behavior:
      • Pull values from saved answers by label or field_code (robust to common variants).
      • Derive the award date split (date_made/month_made/year_made) from a full date if provided.
      • Default the date trio to TODAY (Asia/Manila) if any part is missing.
      • Auto-fill the Barangay Secretary from staff (role_id = 4) if not provided in answers.
      • Sanitize/normalize strings and ensure ALL PDF fields are present.
      • Log the final ordered map that will be injected into the PDF.
    """

    # ---------- Helpers ----------

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
    def _format_name(first: str | None, middle: str | None, last: str | None, suffix: str | None) -> str:
        first = (first or "").strip()
        middle = (middle or "").strip()
        last = (last or "").strip()
        suffix = (suffix or "").strip()
        parts = [first]
        if middle:
            parts.append(middle[0].upper() + ".")
        parts.append(last)
        full = " ".join(p for p in parts if p).strip()
        if suffix:
            full = f"{full} {suffix}".strip()
        return FS.normalize(full)

    def _get_latest_staff_name_by_role(self, role_id: int) -> str:
        """
        Returns the most recent staff's formatted name for a given role_id,
        using staff.person_id -> person to compose "First M. Last Suffix".
        """
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.first_name, p.middle_name, p.last_name, p.suffix
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
                    return ""
                first, middle, last, suffix = row
                return self._format_name(first, middle, last, suffix)
        except Exception as e:
            logger.warning("KP15: failed to fetch staff by role_id=%s: %s", role_id, e)
            return ""

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        """Log/print the final field → value map in the exact order of _KP15_FIELDS."""
        try:
            ordered = {k: out.get(k, "") for k in _KP15_FIELDS}
            print("[KP15] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP15 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP15 logging failed: %s", e)

    # ---------- Main builder ----------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        # Load saved answers for this submission (field_id -> raw string)
        answers_by_id = FS.load_answers(submission_id)

        # Discover labels + codes present on this KP-15 form
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
        for target, sources in _KP15_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Derive/normalize award date split (day/month/year) ---
        day_txt   = (out.get("date_made") or "").strip()
        month_txt = (out.get("month_made") or "").strip()
        year_txt  = (out.get("year_made") or "").strip()

        parsed = None
        # If any of the three fields looks like a full date, parse it.
        if day_txt:
            parsed = self._try_parse_date(day_txt)
        if not parsed and month_txt:
            parsed = self._try_parse_date(month_txt)
        if not parsed and year_txt:
            parsed = self._try_parse_date(year_txt)

        if parsed:
            day_txt   = str(parsed.day)
            month_txt = parsed.strftime("%B")
            year_txt  = str(parsed.year)

        # Default any missing parts to TODAY (PH time)
        now_ph = _dt.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()

        if not day_txt:
            day_txt = str(today.day)
        else:
            # If a full date slipped in here, normalize to day number
            maybe = self._try_parse_date(day_txt)
            if maybe:
                day_txt = str(maybe.day)

        if not month_txt:
            month_txt = today.strftime("%B")
        if not year_txt:
            year_txt = str(today.year)

        out["date_made"] = day_txt
        out["month_made"] = month_txt
        out["year_made"] = year_txt

        # --- Auto-fill secretary if missing: fetch from staff (role_id = 4) ---
        if not out.get("secretary"):
            out["secretary"] = self._get_latest_staff_name_by_role(SECRETARY_ROLE_ID)

        # --- Final sanitize & ensure all fields exist ---
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP15_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for KP-15 submission
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp15_arbitration_award
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
                    notify_kp15_arbitration_award(case_id, case_num)
        except Exception as e:
            logger.warning("[KP15] Failed to send notifications: %s", e)

        # ---- Log what's being filled into the PDF (ordered) ----
        self._log_fill_map(out)

        return out
