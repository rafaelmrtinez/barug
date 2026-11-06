# lupon_mem/services/forms/kp9_2.py
from __future__ import annotations
from typing import Dict, Set, Optional, List
from datetime import date as _date, datetime as _dt
import json
import logging
import calendar

from django.db import connection
from .. import form_shared as FS

logger = logging.getLogger(__name__)

# Exact AcroForm field names in kp_form_no_9_page_2.pdf
_KP9P2_FIELDS = [
    "served_to",
    "date_offcret","month_offcret","ofcret_year",
    "respondent_offcr_ret",
    "offcret_serve_date","offcret_serve_month","offcret_serve_year",
    "respondent_names_one","respondent_names_two","respondent_names_three",
    "proxy_name_one","served_to_2","proxy_name_two","offcr_name",
    "served_to_3","date_signed_one","date_signed_two","served_to_4",
    "number",
]

# Accept both label text and field_code from the builder
_KP9P2_SOURCES: Dict[str, Set[str]] = {
    "served_to": {"served_to", "served_to_1", "recipient", "respondent_recipient"},
    "date_offcret": {"date_offcret", "offcr_return_date"},
    "month_offcret": {"month_offcret", "offcr_return_month"},
    "ofcret_year": {"ofcret_year", "offcr_return_year"},
    "respondent_offcr_ret": {"respondent_offcr_ret", "officer_return_note", "remarks"},
    "offcret_serve_date": {"offcret_serve_date", "serve_date"},
    "offcret_serve_month": {"offcret_serve_month", "serve_month"},
    "offcret_serve_year": {"offcret_serve_year", "serve_year"},
    # lines 1–3 are intentionally *not* auto-sourced from case data here
    "respondent_names_one": {"respondent_names_one"},
    "respondent_names_two": {"respondent_names_two"},
    "respondent_names_three": {"respondent_names_three"},
    "proxy_name_one": {"proxy_name_one"},
    "served_to_2": {"served_to_2"},
    "proxy_name_two": {"proxy_name_two"},
    "offcr_name": {"offcr_name", "officer_name", "process_server"},
    "served_to_3": {"served_to_3"},
    "date_signed_one": {"date_signed_one"},
    "date_signed_two": {"date_signed_two"},
    "served_to_4": {"served_to_4"},
    "number": {"number"},
}

class KP9_2Handler:
    """
    KP-9 (Page 2): OFFICER'S RETURN
    - Uses answers saved for this page.
    - Falls back to case data only for Served To (not for the three respondent lines).
    """

    # ---------------- DB helpers ----------------

    @staticmethod
    def _get_case_id_from_submission(submission_id: int) -> Optional[int]:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [submission_id],
                )
                row = cur.fetchone()
                return int(row[0]) if row and row[0] else None
        except Exception:
            return None

    @staticmethod
    def _prefill_from_case(case_id: int) -> Dict[str, str]:
        """For KP-9-P2 we only need a default 'served_to' (first respondent)."""
        respondents: List[str] = []
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT trim(coalesce(p.first_name,'')||' '||coalesce(p.last_name,'')) AS n
                FROM respondent_case rc
                JOIN person p ON p.person_id = rc.person_id
                WHERE rc.blotter_case_id=%s
                ORDER BY n
                """,
                [case_id],
            )
            respondents = [r[0] for r in cur.fetchall()]

        first_resp = respondents[0] if respondents else ""
        return {
            "served_to": first_resp,
            # keep respondent_names_* empty here; JS will set exactly one line per mode
            "respondent_names_one":   "",
            "respondent_names_two":   "",
            "respondent_names_three": "",
        }

    # ---------------- small utils ----------------

    @staticmethod
    def _try_parse_date(s: str):
        if not s:
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_triplet(out: Dict[str, str], day_key: str, mon_key: str, yr_key: str):
        """If out[day_key] looks like a date string, convert to parts."""
        raw = (out.get(day_key) or "").strip()
        dt = KP9_2Handler._try_parse_date(raw)
        if dt:
            out[day_key] = str(dt.day)
            if not (out.get(mon_key) or "").strip():
                out[mon_key] = dt.strftime("%B")
            if not (out.get(yr_key) or "").strip():
                out[yr_key] = str(dt.year)

    @staticmethod
    def _month_to_name(m: str) -> Optional[str]:
        """Accept 'January'/'jan' or '1'/'01' and return canonical full month name."""
        if not m:
            return None
        mm = m.strip()
        if mm.isdigit():
            i = int(mm)
            if 1 <= i <= 12:
                return calendar.month_name[i]
            return None
        # try to parse textual month
        mm_low = mm.lower()
        for i in range(1, 13):
            if mm_low in (calendar.month_name[i].lower(), calendar.month_abbr[i].lower()):
                return calendar.month_name[i]
        # best effort: title-case the input
        return mm[:1].upper() + mm[1:].lower()

    @staticmethod
    def _format_full_date(day: str, month: str, year: str) -> Optional[str]:
        """Return 'Month D, YYYY' if parts are complete and valid."""
        d = (day or "").strip()
        m = (month or "").strip()
        y = (year or "").strip()

        if not (d and m and y):
            return None
        try:
            dd = int(d)
            yy = int(y)
        except Exception:
            return None

        mname = KP9_2Handler._month_to_name(m)
        if not mname:
            return None
        # Validate day range roughly using current year/month (no need to be perfect for form text)
        try:
            _date(yy, list(calendar.month_name).index(mname), min(dd, 28))  # simple guard
        except Exception:
            pass  # don't fail; we still format as provided

        return f"{mname} {dd}, {yy}"

    @staticmethod
    def _format_processed_time(value) -> str:
        """Read the saved picker value, including older 24-hour answers."""
        raw = FS.sanitize_text(value).removeprefix("@").strip()
        if not raw:
            return ""
        for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S", "%H:%M:%S.%f"):
            try:
                return _dt.strptime(raw, fmt).strftime("%I:%M %p")
            except ValueError:
                continue
        return ""

    @classmethod
    def _format_signed_timestamp(cls, date_text: str, processed_time: str) -> str:
        # An earlier suffix can be replaced without appending another time.
        signed_date = cls._try_parse_date(date_text.partition("@")[0])
        if signed_date is None:
            return date_text
        return f"{signed_date:%B} {signed_date.day}, {signed_date.year} @ {processed_time}"

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP9P2_FIELDS}
            print("[KP9-P2] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP9-P2 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP9-P2 logging failed: %s", e)

    @staticmethod
    def _ensure(out: Dict[str, str], key: str, value: str) -> None:
        if not (out.get(key) or "").strip():
            out[key] = value

    @staticmethod
    def _detect_mode(by_code: Dict[str, str], out: Dict[str, str]) -> Optional[str]:
        """
        Detect selected mode:
        1/2/3/4 from explicit field (service_mode/mode/mode_of_service/service_mode_no),
        else infer from which single-line target was filled by JS.
        """
        for k in ("service_mode", "mode", "mode_of_service", "service_mode_no"):
            v = FS.sanitize_text(by_code.get(k))
            if v in {"1", "2", "3", "4"}:
                return v

        # Infer from line targets placed by JS
        if (out.get("respondent_names_one") or "").strip():
            return "1"
        if (out.get("respondent_names_two") or "").strip():
            return "2"
        if (out.get("respondent_names_three") or "").strip():
            return "3"
        if (out.get("served_to_2") or "").strip():
            return "4"
        return None

    # ---------------- main ----------------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

        # discover label/code + pull saved answers
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

        # Start with what the user actually saved
        out: Dict[str, str] = {}
        for target, sources in _KP9P2_SOURCES.items():
            out[target] = _find_any(sources)

        # Minimal fallback from case data (only served_to)
        case_id = self._get_case_id_from_submission(submission_id)
        if case_id:
            fallback = self._prefill_from_case(case_id)
            for k, v in fallback.items():
                self._ensure(out, k, v)

        # Normalize the two Officer's Return date triplets (split Y-m-d if needed)
        self._normalize_triplet(out, "offcret_serve_date", "offcret_serve_month", "offcret_serve_year")
        self._normalize_triplet(out, "date_offcret", "month_offcret", "ofcret_year")

        # For modes 3 and 4, copy officer return date to serve date if serve date is empty
        mode = self._detect_mode(by_code, out)
        if mode in ["3", "4"]:
            if not (out.get("offcret_serve_date") or "").strip():
                out["offcret_serve_date"] = out.get("date_offcret", "")
            if not (out.get("offcret_serve_month") or "").strip():
                out["offcret_serve_month"] = out.get("month_offcret", "")
            if not (out.get("offcret_serve_year") or "").strip():
                out["offcret_serve_year"] = out.get("ofcret_year", "")

        # ---- NO GENERIC MIRROR FALLBACKS ----

        # Mode-aware behavior (mode already detected above)
        primary = (out.get("served_to") or "").strip()

        # Use the Officer Return date when a signature date has not been saved.
        sig_full = self._format_full_date(
            out.get("date_offcret", ""),
            out.get("month_offcret", ""),
            out.get("ofcret_year", "")
        )
        if sig_full:
            self._ensure(out, "date_signed_one", sig_full)

        # The respondent signs the first line. A proxy signs the second in modes 3 and 4.
        if mode in ["1", "2", "3", "4"]:
            self._ensure(out, "served_to_3", primary)

        if mode == "3":
            # Mode 3: Left at dwelling with (Name) - served_to_4 gets proxy_name_one
            prox = (out.get("proxy_name_one") or "").strip()
            if prox:
                out["served_to_4"] = prox
        elif mode == "4":
            # Mode 4: proxy signs, so served_to_4 gets the proxy name
            prox = (out.get("proxy_name_two") or "").strip()
            if prox:
                out["served_to_4"] = prox

        if mode in {"3", "4"}:
            second_date = sig_full or out["date_signed_one"].partition("@")[0].strip()
            if second_date:
                self._ensure(out, "date_signed_two", second_date)

        # NOTE: We never auto-fill proxy_name_one/proxy_name_two themselves here.

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP9P2_FIELDS:
            out.setdefault(k, "")

        # Format the PDF values using the selected time, without changing the saved answers.
        processed_time = self._format_processed_time(by_code.get("date_time_field"))
        if processed_time:
            out["date_signed_one"] = self._format_signed_timestamp(out["date_signed_one"], processed_time)
            if mode in {"3", "4"}:
                out["date_signed_two"] = self._format_signed_timestamp(out["date_signed_two"], processed_time)

        self._log_fill_map(out)
        return out
