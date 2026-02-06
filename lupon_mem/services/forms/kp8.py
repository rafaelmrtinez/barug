# kp8.py
from __future__ import annotations
from typing import Dict, Set, Any
from datetime import date as _date, datetime as _dt, time as _time
import json
import logging

from .. import form_shared as FS
from django.db import connection  # DB lookups (PB name, case data)

logger = logging.getLogger(__name__)

# Exact AcroForm field names in kp_form_no_8_notice_of_hearing.pdf
_KP8_FIELDS = [
    # parties / addressing
    "recipient", "recipient_2", "complainants", "complainants_2",
    # hearing schedule (triplet + time, shown as: ... the __ day of ____, 20__)
    "appearance_date", "appearance_month", "appearance_year", "appearance_time",
    # “This __ day of ____, ____” line (we fill day → month → year)
    "date_created", "month_created", "year_created",
    # “Notified this ____ day of ____, ____” (month → day → year; CURRENT DATE)
    "date_notified", "month_notified", "year_notified",
    # signature
    "brgy_capt",
]

# Accepted sources to fill targets (read from either field label or code)
_KP8_SOURCES: Dict[str, Set[str]] = {
    "recipient":         {"recipient"},
    "recipient_2":       {"recipient_2"},
    "complainants":      {"complainants", "complainant(s)"},
    "complainants_2":    {"complainants_2", "complainants", "complainant(s)"},
    # Use the Hearing* fields from the form as inputs for the “appearance_*” PDF fields
    "appearance_date":   {"appearance_date", "hearing_date", "hearing date"},
    "appearance_month":  {"appearance_month", "hearing_month", "hearing month"},
    "appearance_year":   {"appearance_year", "hearing_year", "hearing year"},
    # "appearance_time":   {"appearance_time", "hearing_time", "hearing time"},
    "date_created":      {"date_created", "date created", "created_date"},   # Use date_created from form
    "month_created":     {"month_created", "date_created", "date created", "created_date"},  # Use date_created from form
    "year_created":      {"year_created", "date_created", "date created", "created_date"},   # Use date_created from form
    "date_notified":     {"date_notified", "notified_date", "processed_on_date", "processed on date", "processed_date", "date_processed"},  # Use processed_on_date from form
    "month_notified":    {"month_notified", "notified_month", "processed_on_date", "processed on date", "processed_date", "date_processed"}, # Use processed_on_date from form
    "year_notified":     {"year_notified", "notified_year", "processed_on_date", "processed on date", "processed_date", "date_processed"},  # Use processed_on_date from form
    "brgy_capt":         {"brgy_capt", "brgy_captain", "chairman", "punong barangay", "punong_barangay"},
}


_DEFAULT_PUNONG_BARANGAY = "Lourdes Ramirez"


class KP8Handler:
    """
    KP-8: NOTICE OF HEARING (MEDIATION PROCEEDINGS)

    Rules implemented:
      • “Notified this ____ day of ____, ____” → TODAY (Month, Day, Year).
      • “This __ day of ____, ____” line → day → month → year.
      • Hearing “at ____ o’clock” → normalized to HH:MM.
        Fallback chain: appearance_time (answer) → case.time_filed → case.incident_time.
      • If recipient is blank, default to first respondent (when available in answers).
      • brgy_capt mirrors the current Punong Barangay from DB (fallback to default).
    """

    # ---------------- helpers: dates/times ----------------

    @staticmethod
    def _try_parse_date(s: str | None):
        if not s:
            return None
        s = str(s).strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return _dt.strptime(s, fmt).date()
            except Exception:
                pass
        return None

    @staticmethod
    def _parts_from_value(v: str | None):
        """
        Return (day, month_name, year) from a variety of inputs:
        - ISO/US/EU strings → exact parts
        - 'October' → ('', 'October', '')
        - '7' → ('07', '', '')
        - '2025' → ('', '', '2025')
        """
        v = (v or "").strip()
        if not v:
            return "", "", ""
        # Full date strings
        try:
            if len(v) >= 8 and any(ch in v for ch in "-/"):
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        d = _dt.strptime(v, fmt).date()
                        return f"{d.day:02d}", d.strftime("%B"), str(d.year)
                    except Exception:
                        pass
        except Exception:
            pass

        # Year only
        if v.isdigit() and len(v) == 4:
            return "", "", v

        # Month name
        try:
            d = _dt.strptime(v, "%B")
            return "", d.strftime("%B"), ""
        except Exception:
            pass

        # Day only (1-31)
        if v.isdigit():
            n = int(v)
            if 1 <= n <= 31:
                return f"{n:02d}", "", ""

        # Unknown: treat as month text
        return "", v, ""

    @staticmethod
    def _normalize_triplet(out: Dict[str, str], day_key: str, mon_key: str, yr_key: str):
        """
        If out[day_key] looks like a full date string, split it into day / month-name / year.
        Only fills missing month/year so manual overrides stay intact.
        """
        raw = (out.get(day_key) or "").strip()
        dt = KP8Handler._try_parse_date(raw)
        if dt:
            out[day_key] = f"{dt.day:02d}"
            out.setdefault(mon_key, dt.strftime("%B"))
            out.setdefault(yr_key, str(dt.year))

    @staticmethod
    def _fmt_hm(val: Any) -> str:
        """
        Normalize time to HH:MM.
        Accepts: str ('7 PM','19:00','0730'), datetime.time, datetime.datetime.
        """
        if val is None:
            return ""
        if isinstance(val, _time):
            return val.strftime("%H:%M")
        if isinstance(val, _dt):
            return val.time().strftime("%H:%M")

        s = str(val).strip().upper()
        if not s:
            return ""

        for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p", "%I%p", "%I %p", "%H"):
            try:
                t = _dt.strptime(s, fmt).time()
                return t.strftime("%H:%M")
            except Exception:
                continue

        # digits like "730", "0730", "7"
        try:
            if s.isdigit():
                if len(s) <= 2:
                    return _time(hour=int(s) % 24).strftime("%H:%M")
                if len(s) == 3:
                    return _time(hour=int(s[:1]) % 24, minute=int(s[1:]) % 60).strftime("%H:%M")
                if len(s) == 4:
                    return _time(hour=int(s[:2]) % 24, minute=int(s[2:]) % 60).strftime("%H:%M")
        except Exception:
            pass

        # fallback: return as-is
        return s

    @staticmethod
    def _to_12h(val: Any) -> str:
        """
        Return time like '9:30 PM' (12-hour, no leading zero on hour).
        Accepts str, datetime.time, datetime.datetime; empty string on failure.
        """
        s24 = KP8Handler._fmt_hm(val)  # normalize to 'HH:MM' first
        if not s24:
            return ""
        try:
            hh, mm = s24.split(":")
            t = _time(hour=int(hh) % 24, minute=int(mm) % 60)
            # %I keeps leading zero; strip it for '9:30 PM' instead of '09:30 PM'
            return t.strftime("%I:%M %p").lstrip("0")
        except Exception:
            return ""


    def _fetch_punong_barangay_from_db(self) -> str:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT trim(
                        coalesce(p.first_name,'') || ' ' ||
                        coalesce(p.middle_name,'') || ' ' ||
                        coalesce(p.last_name,'')  || ' ' ||
                        coalesce(p.suffix,'')
                    ) AS name
                    FROM staff s
                    JOIN person p ON p.person_id = s.person_id
                    JOIN rolee  r ON r.role_id   = s.role_id
                    WHERE r.role_name = 'BARANGAY CAPTAIN'
                    ORDER BY s.staff_id DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row and (row[0] or "").strip():
                    return row[0].strip()
        except Exception:
            pass
        return _DEFAULT_PUNONG_BARANGAY

    # ---------------- main builder ----------------

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        answers_by_id = FS.load_answers(submission_id)

        # Fetch labels/codes for this form
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

        by_label, by_code = {}, {}
        for fid, label, field_code in rows:
            val = answers_by_id.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                if label:
                    by_label[label.strip().lower()] = val
                if field_code:
                    by_code[field_code.strip().lower()] = val

        def _find_any(keys: Set[str]) -> str:
            for k in keys:
                kk = k.strip().lower()
                if kk in by_label:
                    return FS.normalize(by_label[kk])
                if kk in by_code:
                    return FS.normalize(by_code[kk])
            return ""

        out: Dict[str, str] = {}
        # Seed from sources
        for target, sources in _KP8_SOURCES.items():
            out[target] = _find_any(sources)

        # --- FORCE the "appearance_*" triplet from Hearing Date when available
        # Prefer 'hearing_date' but fall back to whatever went into appearance_date.
        # in KP8Handler.build_name_value_map()

        # Force triplet from Hearing Date …
        hd_raw = _find_any({"hearing_date", "hearing date"}) or out.get("appearance_date") or ""
        if hd_raw:
            d = (self._try_parse_date(hd_raw) or self._try_parse_date(hd_raw.replace("-", "/")))
            if d:
                out["appearance_date"]  = f"{d.day:02d}"
                out["appearance_month"] = d.strftime("%B")
                # IMPORTANT: KP-8 top line expects ONLY the last digit beside the printed "202_"
                out["appearance_year"]  = str(d.year)[-1]

        # --- Normalize/override appearance_time from Hearing Time (if provided)
        # Still inside build_name_value_map(), after computing hearing time
        ht_raw = _find_any({"hearing_time", "hearing time"}) or out.get("appearance_time") or ""
        if ht_raw:
            out["appearance_time"]  = self._to_12h(ht_raw)  # -> '9:30 PM'
            out["appearance_oclock"] = out["appearance_time"]
            out["recipient_2"] = out.get("appearance_time", "")
            out["appearance_oclock"] = out["appearance_time"]


        # Mirror complainants to line 2 if blank
        if not (out.get("complainants_2") or "").strip() and (out.get("complainants") or "").strip():
            out["complainants_2"] = out["complainants"]

        # If recipient missing, try to derive from respondents (if present in this form)
        # We look for "respondents" by either label or code in the same form answers.
        respondents_val = ""
        for key in ("respondents", "respondent(s)"):
            val = _find_any({key})
            if val:
                respondents_val = val
                break
        if not (out.get("recipient") or "").strip() and respondents_val:
            out["recipient"] = respondents_val.split(",")[0].strip()

        # --- CURRENT date for “Notified this … day of …, …”
        # --- Use processed_on_date for "Notified this … day of …, …" instead of current date
        processed_date = None
        processed_date_raw = _find_any({"processed_on_date", "processed on date", "processed_date", "date_processed"})
        if processed_date_raw:
            processed_date = self._try_parse_date(processed_date_raw)
        
        # Fallback to current date if no processed_on_date is provided
        if not processed_date:
            processed_date = _date.today()
            
        out["date_notified"]  = f"{processed_date.day:02d}"   # Day (number with leading zero)
        out["month_notified"]  = processed_date.strftime("%B")   # Month name
        out["year_notified"]  = str(processed_date.year)        # Year

        # --- “This __ day of ____, ____” (we fill DAY → MONTH → YEAR)
        # Prefer any provided date parts; else fall back to Date Filed (case) → today.
        # Pull case info for a better default + time fallback
        case_id = None
        with FS.connection.cursor() as cur2:
            cur2.execute(
                "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                [submission_id],
            )
            row_case = cur2.fetchone()
            if row_case:
                case_id = int(row_case[0])

        filed_date = None
        time_filed = None
        incident_time = None
        if case_id:
            with FS.connection.cursor() as cur2:
                cur2.execute(
                    """
                    SELECT date_filed, time_filed, incident_time
                    FROM blotter_case
                    WHERE blotter_case_id=%s
                    """,
                    [case_id],
                )
                r = cur2.fetchone()
                if r:
                    filed_date, time_filed, incident_time = r[0], r[1], r[2]

        # compute “This …” parts
        dd, mm, yy = self._parts_from_value(out.get("date_created"))
        md, mm2, yy2 = self._parts_from_value(out.get("month_created"))
        yd, ym, yy3 = self._parts_from_value(out.get("year_created"))
        made_day   = dd or md or yd
        made_month = mm or mm2 or ym
        made_year  = yy or yy2 or yy3

        if not (made_day or made_month or made_year):
            src = filed_date or today
            if isinstance(src, _date):
                made_day   = f"{src.day:02d}"
                made_month = src.strftime("%B")
                made_year  = str(src.year)
            else:
                made_day, made_month, made_year = f"{today.day:02d}", today.strftime("%B"), str(today.year)

        # --- Use date_created from form for "This __ day of ____, ____" instead of current date
        created_date = None
        created_date_raw = _find_any({"date_created", "date created", "created_date"})
        if created_date_raw:
            created_date = self._try_parse_date(created_date_raw)
        
        # Fallback to filed_date or current date if no date_created is provided
        if not created_date:
            created_date = filed_date or _date.today()
            
        out["date_created"]  = f"{created_date.day:02d}"      # DAY (01..31)
        out["month_created"] = created_date.strftime("%B")    # MONTH NAME (e.g., October)
        out["year_created"]  = str(created_date.year)         # YEAR (e.g., 2025)

        # Also allow normalizing if user pasted an ISO date into appearance_date
        # self._normalize_triplet(out, "appearance_date", "appearance_month", "appearance_year")

        # --- Hearing time: normalize & fallback chain
        # 1) whatever the user typed (appearance_time)
        # 2) case.time_filed
        # 3) case.incident_time
        if (out.get("appearance_time") or "").strip():
            out["appearance_time"] = self._to_12h(out["appearance_time"])
        else:
            out["appearance_time"] = (
                self._to_12h(time_filed) or
                self._to_12h(incident_time) or
                ""
            )


        # --- Barangay Captain / Punong Barangay
        if not (out.get("brgy_capt") or "").strip():
            out["brgy_capt"] = self._fetch_punong_barangay_from_db()

        # Final sanitize + guarantee all fields exist
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP8_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Send notifications for hearing scheduled
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp8_hearing_scheduled
            if case_id and out.get('appearance_date') and out.get('appearance_time'):
                # Get case number from DB if not in form
                case_num = out.get("brgy_case_number", "")
                if not case_num:
                    with connection.cursor() as cur:
                        cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", [case_id])
                        row = cur.fetchone()
                        case_num = row[0] if row else ""
                
                hearing_date = f"{out.get('appearance_month', '')} {out.get('appearance_date', '')}, 202{out.get('appearance_year', '')}"
                hearing_time = out.get("appearance_time", "")
                notify_kp8_hearing_scheduled(case_id, case_num, hearing_date, hearing_time)
        except Exception as e:
            logger.warning("[KP8] Failed to send notifications: %s", e)

        # ---- PRINT what will be filled into the PDF (ordered) ----
        ordered = {k: out.get(k, "") for k in _KP8_FIELDS}
        print("[KP8] fill map (ordered):\n", json.dumps(ordered, ensure_ascii=False, indent=2))
        try:
            logger.info("KP8 fill map (ordered):\n%s", json.dumps(ordered, ensure_ascii=False, indent=2))
        except Exception:
            pass

        return out
