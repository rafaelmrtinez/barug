# lupon_mem/services/forms/kp9.py
from __future__ import annotations
from typing import Dict, Set, Optional, List
from datetime import date as _date, datetime as _dt
import json
import logging

from django.db import connection
from lupon_mem.services import form_shared as FS
from lupon_mem.services import fields_util as FU  # use KP-8 getters
from lupon_mem.services.forms import util as FormUtil

logger = logging.getLogger(__name__)

# Exact AcroForm field names in kp_form_no_9_summon_for_the_respondent.pdf
_KP9_FIELDS = [
    "complainants","respondents","brgy_case_number","purapose","recipient",
    "summon_date","summon_month","summon_year","summon_time",
    "curr_date","curr_month","curr_year","brgy_capt",
    "served_to","date_offcret","month_offcret","ofcret_year",
    "respondent_offcr_ret","offcret_serve_date","offcret_serve_month","offcret_serve_year",
    "respondent_names_one","respondent_names_two","respondent_names_three",
    "proxy_name_one","served_to_2","proxy_name_two","offcr_name",
    "served_to_3","date_signed_one","date_signed_two","served_to_4",
]

# Accept both label text and field_code from the builder
# NOTE: target key for purpose must be "purapose" to match the PDF field name.
_KP9_SOURCES: Dict[str, Set[str]] = {
    "complainants": {"complainants", "complainant(s)"},
    "respondents": {"respondents", "respondent(s)"},
    "brgy_case_number": {"brgy_case_number", "brgy_case_num", "case_num", "barangay case no."},
    "purpose": {"purpose", "for", "purpose"},  # later copied into "purapose"
    "recipient": {"recipient"},
    "summon_date": {"summon_date"},
    "summon_month": {"summon_month"},
    "summon_year": {"summon_year"},
    "summon_time": {"summon_time", "appearance_time", "notice_time", "time_filed", "time_created"},
    "curr_date": {"curr_date", "current_date", "date_created", "this_date", "date"},
    "curr_month": {"curr_month", "current_month", "month_created"},
    "curr_year": {"curr_year", "current_year", "year_received", "year_created", "year"},
    "brgy_capt": {"brgy_capt", "brgy_captain", "chairman", "punong_barangay"},
    "served_to": {"served_to"},
    "date_offcret": {"date_offcret"},
    "month_offcret": {"month_offcret"},
    "ofcret_year": {"ofcret_year"},
    "respondent_offcr_ret": {"respondent_offcr_ret"},
    "offcret_serve_date": {"offcret_serve_date"},
    "offcret_serve_month": {"offcret_serve_month"},
    "offcret_serve_year": {"offcret_serve_year"},
    "respondent_names_one": {"respondent_names_one"},
    "respondent_names_two": {"respondent_names_two"},
    "respondent_names_three": {"respondent_names_three"},
    "proxy_name_one": {"proxy_name_one"},
    "served_to_2": {"served_to_2"},
    "proxy_name_two": {"proxy_name_two"},
    "offcr_name": {"offcr_name"},
    "served_to_3": {"served_to_3"},
    "date_signed_one": {"date_signed_one"},
    "date_signed_two": {"date_signed_two"},
    "served_to_4": {"served_to_4"},
}

_DEFAULT_PUNONG_BARANGAY = "Lourdes Ramirez"


class KP9Handler:
    """
    KP-9: SUMMON FOR THE RESPONDENT

    Works with the minimal UI where only Summons Date/Time are saved.
    Missing values (complainants/respondents/case no./purpose, PB, today's stamps)
    are fetched from the blotter case and merged into the fill map.

    NEW: If a KP-8 exists for the case, copy:
      hearing_date (YYYY-MM-DD) → summon_date (day), summon_month (Month), summon_year (YYYY)
      hearing_time               → summon_time
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
        """
        Pull minimal-but-complete context from the case so we can fill KP-9
        even if the UI only saved summons date/time.
        """
        complainants: List[str] = []
        respondents: List[str] = []
        case_num = ""
        purpose = ""
        incident_time = None

        with connection.cursor() as cur:
            # header
            cur.execute(
                """
                SELECT bc.blotter_case_num,
                       COALESCE(ct.complaint_title_name,'') AS complaint_title,
                       COALESCE(cn.case_name,'')           AS case_nature,
                       bc.incident_time
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
                WHERE bc.blotter_case_id=%s
                """,
                [case_id],
            )
            h = cur.fetchone()
            if h:
                case_num = (h[0] or "").strip()
                ct = (h[1] or "").strip()
                cn = (h[2] or "").strip()
                incident_time = h[3]
                purpose = f"{ct} - {cn}".strip(" -")

            # parties
            cur.execute(
                """
                SELECT trim(coalesce(p.first_name,'')||' '||coalesce(p.last_name,'')) AS n
                FROM complainant_case cc JOIN person p ON p.person_id=cc.person_id
                WHERE cc.blotter_case_id=%s ORDER BY n
                """,
                [case_id],
            )
            complainants = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT trim(coalesce(p.first_name,'')||' '||coalesce(p.last_name,'')) AS n
                FROM respondent_case rc JOIN person p ON p.person_id=rc.person_id
                WHERE rc.blotter_case_id=%s ORDER BY n
                """,
                [case_id],
            )
            respondents = [r[0] for r in cur.fetchall()]

        def _hm(t):
            try:
                return t.strftime("%H:%M")
            except Exception:
                return None

        return {
            "complainants": ", ".join(complainants),
            "respondents": ", ".join(respondents),
            "brgy_case_number": case_num,
            "purpose": purpose,  # will be copied to "purapose"
            "recipient": (respondents[0] if respondents else ""),
            "summon_time": _hm(incident_time) or "",
        }



    # ---------------- small utils ----------------

    @staticmethod
    def _try_parse_date(s: str):
        if not s:
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_triplet(out: Dict[str, str], day_key: str, mon_key: str, yr_key: str):
        """
        If out[day_key] looks like a date string, convert:
          day_key -> day-of-month (e.g., '9')
          mon_key -> 'October'
          yr_key  -> '2025'
        Leaves existing month/year if already present.
        """
        raw = (out.get(day_key) or "").strip()
        dt = KP9Handler._try_parse_date(raw)
        if dt:
            out[day_key] = str(dt.day)
            if not (out.get(mon_key) or "").strip():
                out[mon_key] = dt.strftime("%B")
            if not (out.get(yr_key) or "").strip():
                out[yr_key] = str(dt.year)

    @staticmethod
    def _log_fill_map(out: Dict[str, str]) -> None:
        try:
            ordered = {k: out.get(k, "") for k in _KP9_FIELDS}
            print("[KP9] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
            logger.info("KP9 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("KP9 logging failed: %s", e)

    @staticmethod
    def _ensure(out: Dict[str, str], key: str, value: str) -> None:
        """Set out[key]=value when it's missing or blank."""
        if not (out.get(key) or "").strip():
            out[key] = value

    # ----------- NEW: overlay summon_* from latest KP-8 -----------
    def _overlay_from_latest_kp8(self, case_id: int, out: Dict[str, str]) -> None:
        """
        Copy KP-8 hearing_date/hearing_time into KP-9 summon_* using fields_util helpers.

        Mapping:
          hearing_date (YYYY-MM-DD) -> summon_date (D), summon_month (Month), summon_year (YYYY)
          hearing_time              -> summon_time
        """
        try:
            rows = FU.get_latest_form_fields(case_id, "KP-8")
            if not rows:
                return

            m = FU.rows_to_text_map(rows)

            # Provided variable style:
            kp8_hearing_date = FS.sanitize_text(m.get("hearing_date") or "")   # e.g., "2025-11-22"
            ap_time          = FS.sanitize_text(m.get("hearing_time") or "")

            # Parse date safely via fields_util helper
            dt = FU.parse_date_safe(kp8_hearing_date)

            # Build appearance_* based on parsed date
            ap_date  = str(dt.day) if dt else ""           # "22"
            ap_month = dt.strftime("%B") if dt else ""     # "November"
            ap_year  = str(dt.year) if dt else ""          # "2025"

            # Convert time to 12-hour format with AM/PM
            if ap_time:
                try:
                    time_obj = _dt.strptime(ap_time, "%H:%M").time()
                    ap_time = time_obj.strftime("%I:%M%p")
                except Exception:
                    pass  # Keep original format if parsing fails

            # Apply to KP-9 summon_* (override when KP-8 provides data)
            if ap_date:
                out["summon_date"] = ap_date
            if ap_month:
                out["summon_month"] = ap_month
            if ap_year:
                out["summon_year"] = ap_year
            if ap_time:
                out["summon_time"] = ap_time

        except Exception as e:
            logger.warning("KP9: failed to overlay from KP-8 via fields_util: %s", e)

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
        for target, sources in _KP9_SOURCES.items():
            out[target] = _find_any(sources)

        # --- Merge DB fallbacks for minimal UI ---
        case_id = self._get_case_id_from_submission(submission_id)
        if case_id:
            fallback = self._prefill_from_case(case_id)
            for k, v in fallback.items():
                self._ensure(out, k, v)

            # Overlay summon_* from latest KP-8 (hearing_* → summon_*)
            self._overlay_from_latest_kp8(case_id, out)

        # Respondents mirrors & default recipient
        resp_val = (out.get("respondents") or "").strip()
        if resp_val:
            self._ensure(out, "respondent_names_one",   resp_val)
            self._ensure(out, "respondent_names_two",   resp_val)
            self._ensure(out, "respondent_names_three", resp_val)
            self._ensure(out, "recipient", resp_val.split(",")[0].strip())

        # Today's stamps if missing (overwrite when blank)
        today = _date.today()
        self._ensure(out, "curr_date",  today.isoformat())
        self._ensure(out, "curr_month", today.strftime("%B"))
        self._ensure(out, "curr_year",  str(today.year))

        # PB name
        pb_from_inputs = ""
        for key in ("punong barangay", "punong_barangay", "brgy_captain", "chairman"):
            v = _find_any({key})
            if v:
                pb_from_inputs = v
                break
        pb_name = pb_from_inputs or FormUtil.get_captain_name(_DEFAULT_PUNONG_BARANGAY)
        self._ensure(out, "brgy_capt", pb_name)

        # Map purpose → PDF typo field "purapose"
        self._ensure(out, "purapose", out.get("purpose", ""))

        # Officer's return ← served triplet if blank
        self._ensure(out, "date_offcret",  out.get("offcret_serve_date", ""))
        self._ensure(out, "month_offcret", out.get("offcret_serve_month", ""))
        self._ensure(out, "ofcret_year",   out.get("offcret_serve_year", ""))

        # Normalize triplets (no change if summon_date is a plain day like "22")
        self._normalize_triplet(out, "summon_date", "summon_month", "summon_year")
        self._normalize_triplet(out, "curr_date",   "curr_month",  "curr_year")
        self._normalize_triplet(out, "offcret_serve_date", "offcret_serve_month", "offcret_serve_year")
        self._normalize_triplet(out, "date_offcret",      "month_offcret",       "ofcret_year")

        # Final sanitize & ensure all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP9_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for summon issued
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp9_summon_issued
            if case_id and out.get('summon_date') and out.get('summon_time'):
                case_num = out.get("brgy_case_number", "")
                hearing_date = f"{out.get('summon_month', '')} {out.get('summon_date', '')}, {out.get('summon_year', '')}".strip()
                hearing_time = out.get("summon_time", "")
                if hearing_date.strip(", "):  # Only notify if we have a proper date
                    notify_kp9_summon_issued(case_id, case_num, hearing_date, hearing_time)
        except Exception as e:
            logger.warning("[KP9] Failed to send notifications: %s", e)

        # Debug log (ordered)
        self._log_fill_map(out)

        return out
