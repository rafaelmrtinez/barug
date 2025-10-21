# lupon_mem/services/prefill.py
from __future__ import annotations
from typing import Dict, List, Tuple
from django.db import connection
from datetime import date as _date

# paste your existing `_prefill_minimal_for_case` body unchanged
def _prefill_minimal_for_case(case_id: int) -> Dict[str, str]:
    """
    Minimal, safe prefill mapping by *field_code* that works well for KP-16 and MEDx-SETTLED.
    Pulls common parties, case no., 'purpose', and a few generic dates.

    Fields produced (aliases included):
      - complainants, complainants_two
      - respondents,  respondents_two
      - brgy_case_num, brgy_case_number, case_num
      - purpose
      - incident_date (ISO), incident_time (HH:MM)
      - punong_barangay / brgy_capt / brgy_captain / chairman
      - date_created / month_created / year_received
      - current_date / current_month / current_year
      - settlement_statement, date_filed, time_filed, date_entered, month_entered, year_entered
    """
    with connection.cursor() as cur:
        # ── Case header
        cur.execute(
            """
            SELECT
              bc.blotter_case_num,
              bc.incident_desc,
              bc.incident_date,
              bc.incident_time,
              COALESCE(ct.complaint_title_name,'') AS complaint_title,
              COALESCE(cn.case_name,'')           AS case_nature
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
            WHERE bc.blotter_case_id = %s
            """,
            [case_id],
        )
        row = cur.fetchone() or (None, None, None, None, "", "")
        case_num, incident_desc, incident_date, incident_time, complaint_title, case_nature = row

        # ── Parties (use full name: first, middle, last, suffix; trim spacing)
        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
                   ) AS name
            FROM complainant_case cc
            JOIN person p ON p.person_id = cc.person_id
            WHERE cc.blotter_case_id = %s
            ORDER BY name
            """,
            [case_id],
        )
        complainants = ", ".join([r[0] for r in cur.fetchall()])

        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
                   ) AS name
            FROM respondent_case rc
            JOIN person p ON p.person_id = rc.person_id
            WHERE rc.blotter_case_id = %s
            ORDER BY name
            """,
            [case_id],
        )
        respondents = ", ".join([r[0] for r in cur.fetchall()])

        # ── PB (Punong Barangay / Barangay Captain)
        cur.execute(
            """
            SELECT TRIM(
                     COALESCE(p.first_name,'') || ' ' ||
                     COALESCE(p.middle_name,'') || ' ' ||
                     COALESCE(p.last_name,'')  || ' ' ||
                     COALESCE(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id   = s.role_id
            WHERE r.role_name = 'BARANGAY CAPTAIN'
            ORDER BY s.staff_id DESC
            LIMIT 1
            """
        )
        row_pb = cur.fetchone()
        punong_barangay = (row_pb[0].strip() if row_pb and row_pb[0] else "") or "LOURDES RAMIREZ"

    # ── Date helpers (use "today" fallbacks)
    today = _date.today()
    today_iso  = today.isoformat()
    today_mon  = today.strftime("%B")
    today_year = str(today.year)

    def _hm(t) -> str | None:
        try:
            return t.strftime("%H:%M")
        except Exception:
            return None

    # ── Purpose (Complaint Title - Case Nature)
    purpose = f"{(complaint_title or '').strip()} - {(case_nature or '').strip()}".strip(" -")

    return {
        # Parties
        "complainants": complainants,
        "respondents": respondents,
        "complainants_two": complainants,
        "respondents_two": respondents,

        # Case no. aliases
        "brgy_case_num": case_num or "",
        "brgy_case_number": case_num or "",
        "case_num": case_num or "",

        # Purpose + incident
        "purpose": purpose,
        "incident_date": (incident_date.isoformat() if hasattr(incident_date, "isoformat") else None) or today_iso,
        "incident_time": _hm(incident_time) or None,

        # Captain / signatures (aliases)
        "punong_barangay": punong_barangay,
        "brgy_capt": punong_barangay,
        "brgy_captain": punong_barangay,
        "chairman": punong_barangay,

        # Generic current stamps
        "date_created": today_iso,
        "month_created": today_mon,
        "year_received": today_year,
        "current_date":  today_iso,
        "current_month": today_mon,
        "current_year":  today_year,

        # KP-16 friendly defaults
        "settlement_statement": (incident_desc or "").strip() or "Amicable settlement reached.",
        "date_filed": today_iso,
        "time_filed": _hm(incident_time) or "14:00",
        "date_entered": today_iso,
        "month_entered": today_mon,
        "year_entered": today_year,
    }



# paste `_slice_until_code` unchanged
def _slice_until_code(fields_with_values: List[tuple], stop_code: str) -> List[tuple]:
    """
    Keep items up to and including the first one whose field_code == stop_code.
    Each item = (kff_id, field_id, label, type_name, is_required, value, field_code)
    """
    stop = (stop_code or "").strip().lower()
    if not stop:
        return fields_with_values
    out: List[tuple] = []
    for item in fields_with_values:
        out.append(item)
        code = (item[6] or "").strip().lower()
        if code == stop:
            break
    return out


