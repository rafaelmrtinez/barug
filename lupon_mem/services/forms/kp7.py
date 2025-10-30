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
    "case_time_filed",                 # ← ensure present
    "complainants_2",
    "date_received", "month_received", "year_received_2",
    "punong_barangay",
]

_KP7_SOURCES = {
    "complainants":      {"complainants", "complainant(s)", "complainant_name", "complainants_2"},
    "respondents":       {"respondents", "respondent(s)", "respondent_name", "respondents_2"},
    "case_num":          {"barangay case no.", "barangay_case_no", "brgy_case_num", "brgy_case_number", "case_num"},
    "purpose":           {"for", "for_section", "purpose", "complaint_title", "case_nature"},
    "complaint_details": {"complaint", "complaint_details"},
    "solutions_seeked":  {"solutions_seeked"},
    "date_created":      {"date_created", "date_signed"},
    "month_created":     {"month_created"},
    "year_received":     {"year_received", "year_created"},
    "case_time_filed":   {"case_time_filed", "time_filed"},
    "complainants_2":    {"complainants_2", "complainants"},
    "date_received":     {"date_received"},
    "month_received":    {"month_received"},
    "year_received_2":   {"year_received_2", "year_received"},
    "punong_barangay":   {"punong_barangay", "brgy_capt", "brgy_captain", "chairman"},
}


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
                if label:
                    by_label[label.strip().lower()] = val
                if field_code:
                    by_code[field_code.strip().lower()] = val

        def _find_any(keys: Set[str]) -> str:
            for k in keys:
                k = k.strip().lower()
                if k in by_label:
                    return FS.normalize(by_label[k])
                if k in by_code:
                    return FS.normalize(by_code[k])
            return ""

        out: Dict[str, str] = {}
        for target, sources in _KP7_SOURCES.items():
            out[target] = _find_any(sources)

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

        # made / received date derivation
        dd1, mo1, yr1 = _parts_from_value(out.get("date_created"))
        dd2, mo2, yr2 = _parts_from_value(out.get("month_created"))
        dd3, mo3, yr3 = _parts_from_value(out.get("year_received"))
        made_day = dd1 or dd2 or dd3
        made_month = mo1 or mo2 or mo3
        made_year = yr1 or yr2 or yr3

        rd1, rm1, ry1 = _parts_from_value(out.get("date_received"))
        rd2, rm2, ry2 = _parts_from_value(out.get("month_received"))
        rd3, rm3, ry3 = _parts_from_value(out.get("year_received_2"))
        recv_day = rd1 or rd2 or rd3
        recv_month = rm1 or rm2 or rm3
        recv_year = ry1 or ry2 or ry3

        made_any = any([made_day, made_month, made_year])
        recv_any = any([recv_day, recv_month, recv_year])

        if made_any and not recv_any:
            recv_day, recv_month, recv_year = made_day, made_month, made_year
        elif recv_any and not made_any:
            made_day, made_month, made_year = recv_day, recv_month, recv_year
        elif not made_any and not recv_any:
            made_day, made_month, made_year = t_day, t_month, t_year
            recv_day, recv_month, recv_year = t_day, t_month, t_year

        out["date_created"] = made_month or t_month
        out["month_created"] = made_day or t_day
        out["year_received"] = made_year or t_year
        out["date_received"] = recv_month or out["date_created"]
        out["month_received"] = recv_day or out["month_created"]
        out["year_received_2"] = recv_year or out["year_received"]

        # ---------------------------------------------------
        # Auto-fill current time
        # ---------------------------------------------------
        if not out.get("case_time_filed"):
            out["case_time_filed"] = t_time

        # ---------------------------------------------------
        # Default Punong Barangay
        # ---------------------------------------------------
        if not (out.get("punong_barangay") or "").strip():
            out["punong_barangay"] = "Lourdes Ramirez"

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

        incident_val = ""
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

        parts = []
        parts.append(f"WHAT: {raw_what}" if raw_what else "WHAT:")
        if when_text:
            parts.append(f"WHEN: {when_text}")
        parts.append(f"WHERE: {where_text}" if where_text else "WHERE:")

        new_details = "\n".join(parts).strip()

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
        FS.save_answers(submission_id, out)
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

        return out
