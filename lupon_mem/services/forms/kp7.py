# lupon_mem/services/forms/kp7.py
from __future__ import annotations
from typing import Dict, Set
from datetime import datetime, date
import logging
import re
from zoneinfo import ZoneInfo  # For PH time

from .. import form_shared as FS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# KP-7: Complaint Form
# ---------------------------------------------------------------

_KP7_FIELDS = [
    "complainants", "respondents", "case_num", "purpose",
    "complaint_details", "solutions_seeked",
    "date_created", "month_created", "year_received",
    "case_time_filed",
    "kp7_date_time_filed",
    "complainants_2",
    "date_received", "month_received", "year_received_2",
    "punong_barangay",
    "processed_on_date",
]

_KP7_SOURCES = {
    "complainants":      {"complainants", "complainant(s)", "complainant_name", "complainants_2"},
    "respondents":       {"respondents", "respondent(s)", "respondent_name", "respondents_2"},
    "case_num":          {"barangay case no.", "barangay_case_no", "brgy_case_num", "brgy_case_number", "case_num"},
    "purpose":           {"for", "for_section", "purpose", "complaint_title", "case_nature"},
    "complaint_details": {"complaint", "complaint_details"},
    "solutions_seeked":  {"solutions_seeked"},
    "date_created":      {"date_created", "date_signed", "date created"},
    "month_created":     {"month_created"},
    "year_received":     {"year_received", "year_created"},
    "case_time_filed":   {"case_time_filed", "time_filed"},
    "kp7_date_time_filed": {"date & time filed", "date and time filed", "date_time_filed"},
    "complainants_2":    {"complainants_2", "complainants"},
    "date_received":     {"date_received", "date received & filed", "date_received_filed", "notified_date"},
    "month_received":    {"month_received", "date received & filed", "date_received_filed", "notified_month"},
    "year_received_2":   {"year_received_2", "year_received", "date received & filed", "date_received_filed", "notified_year"},
    "punong_barangay":   {"punong_barangay", "brgy_capt", "brgy_captain", "chairman"},
    "processed_on_date": {"processed_on_date", "processed on (date)", "processed_on"},
}


def _format_processed_time(value) -> str:
    """Format the entered clock time for the received-and-filed line."""
    raw = FS.sanitize_text(value).removeprefix("@").strip()
    if not raw:
        return ""

    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).strftime("%I:%M %p").lstrip("0")
        except ValueError:
            continue

    # Older submissions may still contain a full filing timestamp in this field.
    return ""


class KP7Handler:
    """
    KP-7: Complaint Form
    Auto-fills current PH date/time, default Punong Barangay,
    and constructs the WHAT/WHEN/WHERE complaint details.
    """

    def build_name_value_map(self, form_id: int, submission_id: int) -> dict:
        assert int(form_id) == 7
        answers_by_id = FS.load_answers(submission_id)

        # ---------------------------------------------------
        # Lookup field definitions
        # ---------------------------------------------------
        with FS.connection.cursor() as cur:
            cur.execute("""
                SELECT f.field_id,
                       LOWER(COALESCE(kff.label_override, f.base_label)) AS label,
                       LOWER(f.field_code)
                  FROM kp_form_field kff
                  JOIN kp_field f ON f.field_id = kff.field_id
                 WHERE kff.form_id=%s
            """, [form_id])
            rows = cur.fetchall()

        by_label, by_code = {}, {}
        for fid, label, field_code in rows:
            val = answers_by_id.get(str(fid))
            if isinstance(val, str):
                val = FS.sanitize_text(val)
            if val not in (None, "", "null"):
                code = (field_code or "").strip().lower()
                # Time Processed may still have a legacy Date and Time Filed label.
                if label and code != "date_time_field":
                    by_label[label.strip().lower()] = val
                if code:
                    by_code[code] = val

        logger.info("[KP7] All answers from DB: %s", {k: v for k, v in by_label.items() if 'date' in k or 'processed' in k})

        def _find_any(keys: Set[str]) -> str:
            for k in keys:
                k = k.strip().lower()
                if k in by_label:
                    return FS.normalize(by_label[k])
                if k in by_code:
                    return FS.normalize(by_code[k])
            return ""

        out: Dict[str, str] = {}
        exact_codes = {"complainants", "respondents", "complainants_2", "kp7_date_time_filed"}
        for target, sources in _KP7_SOURCES.items():
            if target in exact_codes and target in by_code:
                out[target] = FS.normalize(by_code[target])
            else:
                out[target] = _find_any(sources)

        # Remove "CIVIL CASE - " prefix from purpose if present
        if out.get("purpose") and out["purpose"].startswith("CIVIL CASE - "):
            out["purpose"] = out["purpose"][13:]

        # ---------------------------------------------------
        # Propagate duplicates
        # ---------------------------------------------------
        if not out.get("complainants_2") and out.get("complainants"):
            out["complainants_2"] = out["complainants"]
        if not out.get("year_received_2") and out.get("year_received"):
            out["year_received_2"] = out["year_received"]

        # ---------------------------------------------------
        # Date/time preparation
        # ---------------------------------------------------
        now_ph = datetime.now(ZoneInfo("Asia/Manila"))
        today = now_ph.date()
        t_day, t_month, t_year = f"{today.day:02d}", today.strftime("%B"), str(today.year)
        t_time = now_ph.strftime("%I:%M %p")  # 12-hour, e.g. "03:41 PM"

        # date parsing helper
        def _parts_from_value(v: str):
            v = (v or "").strip()
            if not v:
                return ("", "", "")
            try:
                if len(v) >= 8 and any(ch in v for ch in ("-", "/")):
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
                        try:
                            d = datetime.strptime(v, fmt).date()
                            return (f"{d.day:02d}", d.strftime("%B"), str(d.year))
                        except Exception:
                            pass
            except Exception:
                pass
            if v.isdigit() and len(v) == 4:
                return ("", "", v)
            try:
                d = datetime.strptime(v, "%B")
                return ("", d.strftime("%B"), "")
            except Exception:
                pass
            if v.isdigit() and 1 <= int(v) <= 31:
                return (f"{int(v):02d}", "", "")
            return ("", v, "")

        # Parse Date Created and Processed On Date separately
        date_created_val = out.get("date_created") or ""
        logger.info("[KP7] Raw date_created input: '%s'", date_created_val)
        cd, cm, cy = _parts_from_value(date_created_val)
        logger.info("[KP7] Parsed date_created -> day='%s', month='%s', year='%s'", cd, cm, cy)

        processed_on_val = out.get("processed_on_date") or ""
        logger.info("[KP7] Raw processed_on_date input: '%s'", processed_on_val)
        pd, pm, py = _parts_from_value(processed_on_val)
        logger.info("[KP7] Parsed processed_on -> day='%s', month='%s', year='%s'", pd, pm, py)

        # Date Created fills: date_created, month_created, year_received
        # Use date_created if available, otherwise use today
        if cd and cm and cy:
            made_day, made_month, made_year = cd, cm, cy
        else:
            made_day, made_month, made_year = t_day, t_month, t_year

        # Processed On Date fills: date_received, month_received, year_received_2
        # Use processed_on_date if available, otherwise use today (NOT date_created)
        if pd and pm and py:
            recv_day, recv_month, recv_year = pd, pm, py
        else:
            recv_day, recv_month, recv_year = t_day, t_month, t_year

        # Fill PDF-specific fields with parsed parts
        out["date_created"] = made_month  # PDF field: month name
        out["month_created"] = made_day    # PDF field: day number
        out["year_received"] = made_year   # PDF field: year
        out["date_received"] = recv_month  # PDF field: month name
        out["month_received"] = recv_day   # PDF field: day number
        out["year_received_2"] = recv_year # PDF field: year

        logger.info("[KP7] Final values -> date_created='%s', month_created='%s', year_received='%s'",
                    made_month, made_day, made_year)
        logger.info("[KP7] Final values -> date_received='%s', month_received='%s', year_received_2='%s'",
                    recv_month, recv_day, recv_year)

        # ---------------------------------------------------
        # Auto-fill current time
        # ---------------------------------------------------
        if not out.get("case_time_filed"):
            out["case_time_filed"] = t_time

        # ---------------------------------------------------
        # Auto-fill Date & Time Filed from case date_filed and time_filed
        # ---------------------------------------------------
        if not out.get("kp7_date_time_filed"):
            with FS.connection.cursor() as cur2:
                cur2.execute("""
                    SELECT bc.date_filed, bc.time_filed
                      FROM blotter_case bc
                      JOIN blotter_kp_submission s ON s.blotter_case_id = bc.blotter_case_id
                     WHERE s.submission_id = %s
                """, [submission_id])
                row = cur2.fetchone()
                if row and row[0] and row[1]:
                    date_filed, time_filed = row[0], row[1]
                    dt_filed = datetime.combine(date_filed, time_filed)
                    out["kp7_date_time_filed"] = dt_filed.strftime("%B %d, %Y %I:%M %p")
                    logger.info("[KP7] Auto-filled kp7_date_time_filed=%s", out["kp7_date_time_filed"])

        # ---------------------------------------------------
        # Default Punong Barangay
        # ---------------------------------------------------
        if not (out.get("punong_barangay") or "").strip():
            from ..fields_util import get_barangay_captain_name
            out["punong_barangay"] = get_barangay_captain_name()

        # ---------------------------------------------------
        # Complaint Details (WHAT/WHEN/WHERE) — idempotent
        # ---------------------------------------------------
        def _strip_www(s: str) -> str:
            """Remove any existing WHAT/WHEN/WHERE lines so rebuild is idempotent."""
            if not s:
                return ""
            # Drop leading 'WHAT:' on the first line
            s = re.sub(r'(?im)^\s*WHAT\s*:\s*', '', s, count=1)
            # Remove any lines that start with WHEN: or WHERE:
            lines = [ln for ln in s.splitlines() if not re.match(r'^\s*(WHEN|WHERE)\s*:', ln, re.I)]
            return FS.sanitize_text("\n".join(lines).strip())

        # Start from a raw WHAT body (no previous labels)
        raw_what = _strip_www(out.get("complaint_details", "").strip())

        # Get incident date from blotter_report first, then fallback to form fields
        incident_val = ""
        with FS.connection.cursor() as cur2:
            cur2.execute("""
                SELECT br.incident_date
                  FROM blotter_report br
                  JOIN blotter_case bc ON bc.blotter_report_id = br.blotter_report_id
                  JOIN blotter_kp_submission s ON s.blotter_case_id = bc.blotter_case_id
                 WHERE s.submission_id = %s
            """, [submission_id])
            row = cur2.fetchone()
            if row and row[0]:
                incident_val = str(row[0])

        # Fallback to form fields if no blotter report incident date
        if not incident_val:
            if "incident date" in by_label:
                incident_val = FS.normalize(by_label["incident date"])
            elif "incident_date" in by_code:
                incident_val = FS.normalize(by_code["incident_date"])

        if incident_val:
            idd, imo, iyr = _parts_from_value(incident_val)
            when_text = f"{imo} {idd}, {iyr}".strip().replace(" ,", ",")
        else:
            when_text = f"{made_month} {made_day}, {made_year}".strip().replace(" ,", ",")

        where_text = ""
        if "incident location" in by_label:
            where_text = FS.normalize(by_label["incident location"])
        elif "incident_location" in by_code:
            where_text = FS.normalize(by_code["incident_location"])

        if not where_text:
            with FS.connection.cursor() as cur2:
                cur2.execute("""
                    SELECT bc.incident_location, br.incident_address_id
                      FROM blotter_case bc
                      LEFT JOIN blotter_report br
                        ON br.blotter_report_id = bc.blotter_report_id
                      JOIN blotter_kp_submission s
                        ON s.blotter_case_id = bc.blotter_case_id
                     WHERE s.submission_id = %s
                """, [submission_id])
                row = cur2.fetchone()
                if row:
                    bc_loc, addr_id = row
                    if bc_loc:
                        where_text = bc_loc
                    elif addr_id:
                        cur2.execute("""
                            SELECT trim(
                                concat_ws(', ',
                                    NULLIF(ps.purok_sitio_name, ''),
                                    NULLIF(a.street, ''),
                                    CASE WHEN a.barangay IS NOT NULL AND a.barangay <> ''
                                         THEN 'Brgy. ' || a.barangay ELSE NULL END,
                                    NULLIF(a.city, '')
                                )
                            )
                              FROM addresss a
                              LEFT JOIN purok_sitio ps
                                ON ps.purok_sitio_id = a.purok_sitio_id
                             WHERE a.address_id = %s
                        """, [addr_id])
                        addr_row = cur2.fetchone()
                        if addr_row and addr_row[0]:
                            where_text = addr_row[0]

        new_details = raw_what.strip()

        # Only write back if different to avoid churn on repeated runs
        if FS.sanitize_text(out.get("complaint_details", "")) != new_details:
            out["complaint_details"] = new_details

        # ---------------------------------------------------
        # Sanitize + ensure all fields exist
        # ---------------------------------------------------
        for k, v in list(out.items()):
            if isinstance(v, str):
                out[k] = FS.sanitize_text(v)
        for k in _KP7_FIELDS:
            out.setdefault(k, "")

        # ---------------------------------------------------
        # Save all computed answers into DB
        # ---------------------------------------------------
        # Don't save date_created if it's just a month name - preserve original date
        save_out = out.copy()
        if date_created_val and len(date_created_val) >= 8:
            save_out["date_created"] = date_created_val  # Preserve original date
            logger.info("[KP7] Preserving date_created='%s' (original input)", date_created_val)
        else:
            save_out["date_created"] = made_month  # Use month if no date
            logger.info("[KP7] Using month for date_created='%s'", made_month)

        logger.info("[KP7] Saving to DB: date_created='%s', processed_on_date='%s'",
                    save_out.get("date_created"), save_out.get("processed_on_date"))
        FS.save_answers(submission_id, save_out)
        logger.info("[KP7] Auto-filled & saved case_time_filed=%s (submission=%s)", out.get("case_time_filed"), submission_id)

        # ---------------------------------------------------
        # Send notifications for complaint filing
        # ---------------------------------------------------
        try:
            from notifications.views import notify_kp7_complaint_filed
            with FS.connection.cursor() as cur:
                cur.execute(
                    "SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
                    [submission_id]
                )
                row = cur.fetchone()
                if row:
                    case_id = row[0]
                    case_num = out.get("case_num", "")
                    notify_kp7_complaint_filed(case_id, case_num)
        except Exception as e:
            logger.warning("[KP7] Failed to send notifications: %s", e)

        # Apply PDF widget mappings only after saving the original names and year.
        pdf_out = out.copy()
        pdf_out["Text1"] = out["complainants"]
        pdf_out["respondents_extra"] = out["respondents"]
        pdf_out["respondents"] = FS.sanitize_text(by_code.get("recipient_address"))

        complainant_address = FS.sanitize_text(by_code.get("contact_one"))
        pdf_out["complainants"] = complainant_address
        pdf_out["complainant"] = complainant_address  # Also support the singular widget name.

        processed_time = _format_processed_time(by_code.get("date_time_field"))
        if processed_time:
            pdf_out["year_received_2"] = f"{recv_year} @{processed_time}"

        return pdf_out
