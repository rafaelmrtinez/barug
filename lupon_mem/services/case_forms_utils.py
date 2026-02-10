# lupon_mem/services/case_forms_utils.py
from __future__ import annotations
from typing import Dict, List, Any
from datetime import datetime
from django.db import connection
from lupon_mem.services import form_shared as FS

def format_date(date_str: str) -> str:
    """Format date from YYYY-MM-DD to 'Month Day, Year'."""
    if not date_str:
        return ""
    # Strip quotes if present
    date_str = date_str.strip('"')
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B %d, %Y")
    except:
        return date_str

def format_time(time_str: str) -> str:
    """Format time from HH:MM to 'HH:MM AM/PM'."""
    if not time_str:
        return ""
    # Strip quotes if present
    time_str = time_str.strip('"')
    try:
        dt = datetime.strptime(time_str, "%H:%M")
        return dt.strftime("%I:%M %p")
    except:
        return time_str

def fetch_case_kp8_data(case_id: int) -> List[Dict[str, Any]]:
    """Get all KP-8 dates and times for a case."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id, a.value_json, fld.field_code 
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
            JOIN kp_field fld ON fld.field_id = a.field_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-8'
            AND fld.field_code IN ('date_notified', 'hearing_date', 'hearing_time')
            ORDER BY s.submission_id, fld.field_code
        """, [case_id])
        
        kp8_data = {}
        for sid, val, fcode in cur.fetchall():
            kp8_data.setdefault(sid, {})[fcode] = FS.normalize(val)
        
        result = [{
            "date_notified": d.get('date_notified', ''),
            "hearing_date": d.get('hearing_date', ''),
            "hearing_time": d.get('hearing_time', '')
        } for d in kp8_data.values()]
        print(f"[fetch_case_kp8_data] case_id={case_id} result={result}")
        return result

def fetch_case_kp9_data(case_id: int) -> List[str]:
    """Get all KP-9 summon dates for a case."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT a.value_json FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
            JOIN kp_field fld ON fld.field_id = a.field_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-9' 
            AND fld.field_code = 'curr_date'
            ORDER BY s.submission_id
        """, [case_id])
        result = [FS.normalize(r[0]) for r in cur.fetchall()]
        print(f"[fetch_case_kp9_data] case_id={case_id} result={result}")
        return result

def fetch_case_kp9p2_data(case_id: int) -> List[str]:
    """Get all KP-9-P2 officer return dates for a case."""
    with connection.cursor() as cur:
        # First try offcr_ret_date, then try field_id 291 directly
        cur.execute("""
            SELECT s.submission_id, a.value_json, fld.field_code, fld.field_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
            JOIN kp_field fld ON fld.field_id = a.field_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-9-P2' 
            AND (fld.field_code = 'offcr_ret_date' OR fld.field_id = 291)
            ORDER BY s.submission_id
        """, [case_id])
        
        result = [FS.normalize(r[1]) for r in cur.fetchall()]
        print(f"[fetch_case_kp9p2_data] case_id={case_id} result={result}")
        return result

def fetch_case_kp16_data(case_id: int) -> Dict[str, str]:
    """Get the latest KP-16 settlement data for a case."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.submission_id
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-16'
            ORDER BY s.submission_id DESC LIMIT 1
        """, [case_id])
        row = cur.fetchone()
        if not row:
            return {"settlement_dt": "", "settlement_statement": ""}
        
        submission_id = row[0]
        cur.execute("""
            SELECT fld.field_code, a.value_json
            FROM blotter_kp_answer a
            JOIN kp_field fld ON fld.field_id = a.field_id
            WHERE a.submission_id = %s
            AND fld.field_code IN ('date_entered', 'month_entered', 'year_entered', 'settlement_statement')
        """, [submission_id])
        
        data = {}
        for field_code, value in cur.fetchall():
            data[field_code] = FS.normalize(value).strip('"')
        
        # Combine date parts into formatted date
        settlement_dt = ""
        if data.get('date_entered') and data.get('month_entered') and data.get('year_entered'):
            try:
                date_str = f"{data['year_entered']}-{data['month_entered']}-{data['date_entered']}"
                dt = datetime.strptime(date_str, "%Y-%B-%d")
                settlement_dt = dt.strftime("%B %d, %Y")
            except:
                settlement_dt = f"{data['month_entered']} {data['date_entered']}, {data['year_entered']}"
        
        return {
            "settlement_dt": settlement_dt,
            "settlement_statement": data.get('settlement_statement', '')
        }

def fetch_case_kp7_data(case_id: int) -> Dict[str, str]:
    """Get KP-7 case filing data."""
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT s.submission_id
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id = s.form_id
                WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-7'
                ORDER BY s.submission_id LIMIT 1
            """, [case_id])
            row = cur.fetchone()
            if not row:
                return {"dt_filed": "", "complainant_name": "", "respondent_name": "", "complaint_title": ""}
            
            submission_id = row[0]
            cur.execute("""
                SELECT fld.field_id, fld.field_code, fld.base_label, a.value_json
                FROM blotter_kp_answer a
                JOIN kp_field fld ON fld.field_id = a.field_id
                WHERE a.submission_id = %s
            """, [submission_id])
            
            data = {}
            for field_id, field_code, base_label, value in cur.fetchall():
                val = FS.normalize(value).strip('"')
                if field_id == 1:
                    data['complainant_name'] = val
                elif field_id == 2:
                    data['respondent_name'] = val
                elif field_id == 169:
                    data['complaint_title'] = val
                elif base_label and 'date' in base_label.lower() and 'time' in base_label.lower() and 'filed' in base_label.lower():
                    data['dt_filed'] = val
            
            return {
                "dt_filed": data.get('dt_filed', ''),
                "complainant_name": data.get('complainant_name', ''),
                "respondent_name": data.get('respondent_name', ''),
                "complaint_title": data.get('complaint_title', '')
            }
    except Exception as e:
        print(f"[fetch_case_kp7_data] ERROR: {e}")
        return {"dt_filed": "", "complainant_name": "", "respondent_name": "", "complaint_title": ""}

def fetch_case_number(case_id: int) -> str:
    """Get case number for a case."""
    with connection.cursor() as cur:
        cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id = %s", [case_id])
        row = cur.fetchone()
        return row[0] if row else ""

def fetch_all_case_forms_data(case_id: int) -> Dict[str, Any]:
    """Get all KP-7, KP-8, KP-9, KP-9-P2, and KP-16 data for a case."""
    print(f"[fetch_all_case_forms_data] START case_id={case_id}")
    result = {
        "case_number": fetch_case_number(case_id),
        "kp7": fetch_case_kp7_data(case_id),
        "kp8": fetch_case_kp8_data(case_id),
        "kp9": fetch_case_kp9_data(case_id),
        "kp9p2": fetch_case_kp9p2_data(case_id),
        "kp16": fetch_case_kp16_data(case_id),
    }
    print(f"[fetch_all_case_forms_data] END result={result}")
    return result
