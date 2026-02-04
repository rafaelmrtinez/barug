# lupon_mem/services/form_builder_service.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Tuple
import json
from datetime import date as _date_cls, datetime as _dt_cls

HeaderNorm = Tuple[str, str, Optional[str]]  # (form_code, form_name, display_title?)

def fetch_header(cur, form_id: Optional[int], submission_id: Optional[int]) -> Tuple[int, HeaderNorm, str]:
    if submission_id:
        cur.execute(
            """
            SELECT s.submission_id, s.form_id, kf.form_code, kf.form_name
              FROM blotter_kp_submission s
              JOIN kp_form kf ON kf.form_id = s.form_id
             WHERE s.submission_id=%s
            """,
            [submission_id],
        )
    else:
        cur.execute(
            "SELECT kf.form_id, kf.form_code, kf.form_name FROM kp_form kf WHERE kf.form_id=%s",
            [form_id],
        )
    hdr = cur.fetchone()
    if not hdr:
        raise ValueError("Form not found.")

    fid       = hdr[1] if submission_id else hdr[0]
    form_code = hdr[2] if submission_id else hdr[1]
    form_name = hdr[3] if submission_id else hdr[2]
    hdr_norm: HeaderNorm = (form_code or f"KP-{fid}", form_name, None)
    return fid, hdr_norm, form_code

def fetch_fields(cur, fid: int) -> Sequence[Tuple[int,int,str,str,bool,str]]:
    cur.execute(
        """
        SELECT
            kff.kp_form_field_id,
            f.field_id,
            COALESCE(kff.label_override, f.base_label) AS label,
            t.field_type_name,
            kff.is_required,
            f.field_code
        FROM kp_form_field kff
        JOIN kp_field f      ON f.field_id = kff.field_id
        JOIN kp_field_type t ON t.field_type_id = f.field_type_id
        WHERE kff.form_id=%s
        ORDER BY kff.sort_order, kff.kp_form_field_id
        """,
        [fid],
    )
    return cur.fetchall()

def fetch_saved_answers(cur, submission_id: Optional[int]) -> Dict[str, Any]:
    answers: Dict[str, Any] = {}
    if submission_id:
        cur.execute(
            "SELECT a.field_id, a.value_json FROM blotter_kp_answer a WHERE a.submission_id=%s",
            [submission_id],
        )
        for f_id, val in cur.fetchall():
            answers[str(f_id)] = val
    return answers

def fetch_case_core(cur, case_id: int):
    cur.execute(
        """
        SELECT
            bc.blotter_case_num,
            bc.incident_desc,
            bc.incident_date,
            bc.incident_time,
            bc.incident_location,
            bc.date_filed,
            ct.complaint_title_name,
            cn.case_name,
            bc.blotter_report_id,
            bc.time_filed
        FROM blotter_case bc
        LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
        LEFT JOIN case_nature   cn   ON cn.case_nature_id   = bc.case_nature_id
        WHERE bc.blotter_case_id=%s
        """,
        [case_id],
    )
    row = cur.fetchone()
    return row if row else (None,)*10

def resolve_incident_address(cur, blotter_report_id: Optional[int]) -> Optional[str]:
    if not blotter_report_id:
        return None
    cur.execute(
        "SELECT incident_address_id FROM blotter_report WHERE blotter_report_id=%s",
        [blotter_report_id],
    )
    r = cur.fetchone()
    incident_address_id = r[0] if r else None
    if not incident_address_id:
        return None
    cur.execute(
        """
        SELECT trim(
                 concat_ws(', ',
                   NULLIF(ps.purok_sitio_name,''),
                   NULLIF(a.street,''),
                   CASE WHEN a.barangay IS NOT NULL AND a.barangay <> '' THEN 'Brgy. '||a.barangay ELSE NULL END,
                   NULLIF(a.city,'')
                 )
               ) AS full_addr
          FROM addresss a
          LEFT JOIN purok_sitio ps ON ps.purok_sitio_id = a.purok_sitio_id
         WHERE a.address_id = %s
        """,
        [incident_address_id],
    )
    ar = cur.fetchone()
    return (ar and ar[0]) or None

def fetch_party_names(cur, case_id: int) -> Tuple[List[str], List[str]]:
    cur.execute(
        """
        SELECT p.first_name, p.last_name
          FROM complainant_case cc
          JOIN person p ON p.person_id = cc.person_id
         WHERE cc.blotter_case_id=%s
         ORDER BY p.last_name, p.first_name
        """,
        [case_id],
    )
    cmps = ["%s %s" % (fn or "", ln or "") for fn, ln in cur.fetchall()]
    cur.execute(
        """
        SELECT p.first_name, p.last_name
          FROM respondent_case rc
          JOIN person p ON p.person_id = rc.person_id
         WHERE rc.blotter_case_id=%s
         ORDER BY p.last_name, p.first_name
        """,
        [case_id],
    )
    resps = ["%s %s" % (fn or "", ln or "") for fn, ln in cur.fetchall()]
    return cmps, resps

def fetch_party_json(cur, case_id: int) -> Tuple[str, str]:
    cur.execute(
        """
        SELECT p.person_id, p.first_name, COALESCE(p.middle_name,''), p.last_name, COALESCE(p.suffix,'')
          FROM complainant_case cc
          JOIN person p ON p.person_id = cc.person_id
         WHERE cc.blotter_case_id=%s
         ORDER BY p.last_name, p.first_name
        """,
        [case_id],
    )
    _c_rows = cur.fetchall()
    complainants_list = [
        {"person_id": pid, "name": " ".join(x for x in [fn, mn, ln, sx] if (x or "").strip()).strip()}
        for (pid, fn, mn, ln, sx) in _c_rows
    ]
    cur.execute(
        """
        SELECT p.person_id, p.first_name, COALESCE(p.middle_name,''), p.last_name, COALESCE(p.suffix,'')
          FROM respondent_case rc
          JOIN person p ON p.person_id = rc.person_id
         WHERE rc.blotter_case_id=%s
         ORDER BY p.last_name, p.first_name
        """,
        [case_id],
    )
    _r_rows = cur.fetchall()
    respondents_list = [
        {"person_id": pid, "name": " ".join(x for x in [fn, mn, ln, sx] if (x or "").strip()).strip()}
        for (pid, fn, mn, ln, sx) in _r_rows
    ]
    return json.dumps(complainants_list, ensure_ascii=False), json.dumps(respondents_list, ensure_ascii=False)

def fetch_punong_barangay(cur) -> str:
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
    row_pb = cur.fetchone()
    return (row_pb[0].strip() if row_pb and row_pb[0] else "") or "Lourdes Ramirez"

def _iso_date(d):
    try: return d.isoformat()
    except Exception: return None

def _hm(t):
    try: return t.strftime("%H:%M")
    except Exception: return None

def _fmt_purpose(ct_name: Optional[str], cn_name: Optional[str]) -> str:
    b = (cn_name or "").strip()
    return b or ""

def build_prefills(
    *,
    case_num: Optional[str],
    incident_desc: Optional[str],
    incident_date,
    incident_time,
    incident_loc: Optional[str],
    date_filed,
    time_filed,
    complaint_title_name: Optional[str],
    case_nature_name: Optional[str],
    punong_barangay: str,
    parties_complainant: str,
    parties_respondent: str,
    first_respondent: str,
) -> Tuple[Dict[str,Any], Dict[str,Any], str, str, str, str, str, str]:
    # date sources
    src_date = date_filed or incident_date or _date_cls.today()
    try:
        if isinstance(src_date, str):
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    src_date = _dt_cls.strptime(src_date, fmt).date()
                    break
                except Exception:
                    pass
        if not hasattr(src_date, "year"):
            src_date = _date_cls.today()
    except Exception:
        src_date = _date_cls.today()

    date_created_iso = _iso_date(src_date) or _date_cls.today().isoformat()
    month_created    = src_date.strftime("%B")
    year_received    = str(src_date.year)
    month_received   = month_created

    today = _date_cls.today()
    curr_date_iso = today.isoformat()
    curr_month    = today.strftime("%B")
    curr_year     = str(today.year)

    for_value = _fmt_purpose(complaint_title_name, case_nature_name)

    # Create concatenated date & time filed string like "Jan 13, 2025 @02:35 PM"
    date_time_filed_str = ""
    if date_filed and time_filed:
        try:
            # Parse date
            if isinstance(date_filed, str):
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        date_obj = _dt_cls.strptime(date_filed, fmt).date()
                        break
                    except Exception:
                        pass
            else:
                date_obj = date_filed
            
            # Parse time
            if isinstance(time_filed, str):
                try:
                    time_obj = _dt_cls.strptime(time_filed, "%H:%M:%S").time()
                except Exception:
                    try:
                        time_obj = _dt_cls.strptime(time_filed, "%H:%M").time()
                    except Exception:
                        time_obj = time_filed
            else:
                time_obj = time_filed
            
            # Format as "Jan 13, 2025 @02:35 PM"
            date_str = date_obj.strftime("%b %d, %Y")
            time_str = time_obj.strftime("%I:%M %p")
            date_time_filed_str = f"{date_str} @{time_str}"
        except Exception:
            pass

    # Extract day from dates for forms that need it
    date_created_day = str(src_date.day).zfill(2) if src_date else ""
    date_notified_day = str(today.day).zfill(2)
    
    prefill_by_label: Dict[str, Any] = {
        "complainant(s)": parties_complainant,
        "complainants": parties_complainant,
        "respondent(s)": parties_respondent,
        "respondents": parties_respondent,
        "complainant(s) - alternate": parties_complainant,
        "complainants - alternate": parties_complainant,
        "complainant(s) – alternate": parties_complainant,
        "complainants – alternate": parties_complainant,
        "barangay case no.": (case_num or ""),
        "brgy case number": (case_num or ""),
        "brgy case no.": (case_num or ""),
        "case number": (case_num or ""),
        "case no.": (case_num or ""),
        "for": for_value,
        "purpose": for_value,
        "complaint details": (incident_desc or ""),
        "complaint": (incident_desc or ""),
        "incident description": (incident_desc or ""),
        "incident date": _iso_date(incident_date) or "",
        "incident time": _hm(incident_time) or "",
        "incident location": (incident_loc or ""),
        "date created": date_created_iso,
        "month created": month_created,
        "year received": year_received,
        "month received": month_received,
        "year received - alternate": year_received,
        "year received – alternate": year_received,
        "punong barangay": punong_barangay,
        "barangay captain": punong_barangay,
        "chairman": punong_barangay,
        "brgy capt": punong_barangay,
        "current date": curr_date_iso,
        "current month": curr_month,
        "current year": curr_year,
        "date signed": date_created_iso,
        "recipient": first_respondent,
        "processed on (date)": curr_date_iso,
        "date & time filed": date_time_filed_str,
        "date and time filed": date_time_filed_str,
    }

    prefill_by_code: Dict[str, Any] = {
        "complainants": parties_complainant,
        "respondents": parties_respondent,
        "brgy_case_number": (case_num or ""),
        "brgy_case_num": (case_num or ""),
        "case_num": (case_num or ""),
        "purpose": for_value,
        "complaint_details": (incident_desc or ""),
        "incident_date": _iso_date(incident_date) or "",
        "incident_time": _hm(incident_time) or "",
        "incident_location": (incident_loc or ""),
        "date_created": date_created_day,  # Use day only for date_created
        "month_created": month_created,
        "year_created": str(src_date.year),
        "year_received": year_received,
        "month_received": month_received,
        "complainants_2": parties_complainant,
        "year_received_2": year_received,
        "punong_barangay": punong_barangay,
        "date_signed": date_created_iso,
        "recipient": first_respondent,
        "respondent_names_one": parties_respondent,
        "respondent_names_two": parties_respondent,
        "respondent_names_three": parties_respondent,
        "curr_date":  curr_date_iso,
        "curr_month": curr_month,
        "curr_year":  curr_year,
        "brgy_capt": punong_barangay,
        "processed_on_date": curr_date_iso,
        # KP-12
        "complainants_one": parties_complainant,
        "repondents_one":   parties_respondent,
        "complainants_two": parties_complainant,
        "respondents_two":  parties_respondent,
        "time_created": _hm(incident_time) or None,
        "current_date":  curr_date_iso,
        "current_month": curr_month,
        "current_year":  curr_year,

        "notified_date":  curr_date_iso,
        "notified_month": curr_month,
        "notified_year":  curr_year,
        "brgy_captain": punong_barangay,
        "date_time_filed": date_time_filed_str,
        "date_and_time_filed": date_time_filed_str,
    }

    return (prefill_by_label, prefill_by_code,
            date_created_iso, month_created, year_received, month_received,
            curr_month, curr_year)

def apply_answers_and_prefills(
    fields: Sequence[Tuple[int,int,str,str,bool,str]],
    answers: Dict[str, Any],
    prefill_by_label: Dict[str,Any],
    prefill_by_code: Dict[str,Any],
    form_id: int = None,
    submission_id: int = None,
    form_code: str = None,
):
    # For KP-24, use handler to populate fields
    handler_values = {}
    if form_code == "KP-24" and submission_id:
        try:
            from lupon_mem.services.forms import get_handler
            handler = get_handler(form_code)
            handler_values = handler.build_name_value_map(form_id, submission_id)
        except Exception:
            pass
    
    def _ans_or_prefill(field_id, label, code):
        v = answers.get(str(field_id))
        
        # If there's a saved answer, always use it
        if v not in (None, "", "null"):
            return v
        
        # Check handler values first for KP-24
        if handler_values:
            code_lower = (code or "").strip().lower()
            label_lower = (label or "").strip().lower()
            # Map common field codes to handler keys
            if code_lower == "complainants" or label_lower == "complainant(s)":
                return handler_values.get("complaints", "")
            elif code_lower == "respondents" or label_lower == "respondent(s)":
                return handler_values.get("respondents", "")
            elif code_lower in ("case_num", "brgy_case_num", "case_number"):
                return handler_values.get("case_num", "")
            elif code_lower == "purpose":
                return handler_values.get("purpose", "")
        
        # Don't prefill date_entered, month_entered, year_entered, date_signed, time_signed, when - these should come from user input
        if submission_id:
            code_lower = (code or "").strip().lower()
            label_lower = (label or "").strip().lower()
            if code_lower in ("date_created", "processed_on_date", "date_entered", "month_entered", "year_entered", "date_signed", "time_signed", "when") or label_lower in ("date created", "processed on (date)", "date signed", "time signed", "when"):
                # No saved answer and submission exists = user hasn't filled it yet or cleared it
                # Don't prefill to avoid overwriting
                return None
        
        key = (label or "").strip().lower()
        if key in prefill_by_label:
            return prefill_by_label[key]
        ckey = (code or "").strip().lower()
        return prefill_by_code.get(ckey, "")

    fields_with_values = [
        (
            kff_id, field_id, label, type_name, is_required,
            _ans_or_prefill(field_id, label, field_code),
            field_code,
        )
        for (kff_id, field_id, label, type_name, is_required, field_code) in fields
    ]
    return fields_with_values

def find_page2_index(fields_with_values) -> Optional[int]:
    for idx, (_kff, _fid, _lbl, _typ, _req, _val, code) in enumerate(fields_with_values, start=1):
        if (code or "").strip().lower() == "served_to":
            return idx
    return None

def slice_until_code(fields_with_values, stop_code: str):
    stop = (stop_code or "").strip().lower()
    out = []
    for row in fields_with_values:
        out.append(row)
        code = (row[6] or "").strip().lower()
        if code == stop:
            break
    return out

def compute_ui_flags(form_code: str) -> Dict[str,bool]:
    u = str(form_code).strip().upper()
    return {
        "kp7_ui_minimal":  (u == "KP-7"),
        "kp9_ui_minimal":  (u == "KP-9"),
        "kp8_ui_minimal":  (u == "KP-8"),
        "kp10_ui_minimal": False,  # Temporarily disabled
        "kp11_ui_minimal": False,  # Temporarily disabled
        "kp12_ui_minimal": False,  # Temporarily disabled
        "kp13_ui_minimal": False,  # Temporarily disabled
        "kp14_ui_minimal": False,  # Temporarily disabled
        "kp15_ui_minimal": False,  # Temporarily disabled
        "kp16_ui_minimal": (u == "KP-16"),
        "kp17_ui_minimal": False,  # Temporarily disabled
        "kp18_ui_minimal": False,  # Temporarily disabled
        "kp19_ui_minimal": False,  # Temporarily disabled
        "kp20_ui_minimal": False,  # Temporarily disabled
        "kp20a_ui_minimal": False,  # Temporarily disabled
        "kp20b_ui_minimal": False,  # Temporarily disabled
        "kp21_ui_minimal": False,  # Temporarily disabled
        "kp22_ui_minimal": False,  # Temporarily disabled
        "kp23_ui_minimal": False,  # Temporarily disabled
        "kp24_ui_minimal": False,  # Temporarily disabled
        "kp25_ui_minimal": False,  # Temporarily disabled
        "kp26_ui_minimal": False,  # Temporarily disabled
        "minutes_ui_minimal": (u == "MINUTES"),
    }
