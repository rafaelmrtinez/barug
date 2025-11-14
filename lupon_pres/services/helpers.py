# lupon_pres/services/helpers.py
"""
Helper functions for lupon_pres - mirrors lupon_mem.services.helpers
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection
import logging

log = logging.getLogger(__name__)

def ordinal(n: int) -> str:
    """Convert number to ordinal (1st, 2nd, 3rd, etc.)"""
    if n % 100 in (11, 12, 13):
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def one_val(sql: str, params: Optional[List] = None) -> Any:
    """Execute SQL and return single value"""
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as e:
        log.exception("Error in one_val")
        return None

def row(sql: str, params: Optional[List] = None) -> Optional[Tuple]:
    """Execute SQL and return single row"""
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchone()
    except Exception as e:
        log.exception("Error in row")
        return None

def rows(sql: str, params: Optional[List] = None) -> List[Tuple]:
    """Execute SQL and return all rows"""
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    except Exception as e:
        log.exception("Error in rows")
        return []

def get_form_id(form_code: str) -> Optional[int]:
    """Get form ID by form code"""
    return one_val(
        "SELECT form_id FROM kp_form WHERE UPPER(form_code) = UPPER(%s) LIMIT 1",
        [form_code]
    )

def submitted_codes(case_id: int) -> Dict[str, bool]:
    """Get submitted form codes for a case"""
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT UPPER(f.form_code) as code, 
                       BOOL_OR(UPPER(s.status) = 'SUBMITTED') as is_submitted
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id = s.form_id
                WHERE s.blotter_case_id = %s
                GROUP BY f.form_code
            """, [case_id])
            
            return {row[0]: bool(row[1]) for row in cur.fetchall()}
    except Exception as e:
        log.exception("Error in submitted_codes")
        return {}

def latest_submission_for_codes(case_id: int, codes: List[str]) -> Optional[Tuple]:
    """Get latest submission for given form codes"""
    codes_upper = [c.upper() for c in codes]
    return row("""
        SELECT s.submission_id, UPPER(f.form_code) as code, s.submitted_at
        FROM blotter_kp_submission s
        JOIN kp_form f ON f.form_id = s.form_id
        WHERE s.blotter_case_id = %s
          AND UPPER(f.form_code) = ANY(%s)
          AND UPPER(s.status) = 'SUBMITTED'
        ORDER BY s.submitted_at DESC NULLS LAST, s.submission_id DESC
        LIMIT 1
    """, [case_id, codes_upper])

def latest_notice_submitted_at(case_id: int) -> Optional[Any]:
    """Get latest notice submission timestamp"""
    return one_val("""
        WITH forms AS (
          SELECT form_id FROM kp_form WHERE UPPER(form_code) IN ('KP-8','KP-12')
        )
        SELECT MAX(s.submitted_at)
        FROM blotter_kp_submission s
        WHERE s.blotter_case_id = %s
          AND s.form_id IN (SELECT form_id FROM forms)
          AND UPPER(s.status) = 'SUBMITTED'
    """, [case_id])

def is_hearing_held(case_id: int, strict: bool = True) -> bool:
    """Check if hearing was held"""
    latest_notice_at = latest_notice_submitted_at(case_id)
    
    if strict and latest_notice_at:
        return bool(one_val("""
            SELECT 1
            FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id = %s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
              AND cpt.date_processed > %s
            LIMIT 1
        """, [case_id, latest_notice_at]))
    else:
        return bool(one_val("""
            SELECT 1
            FROM case_progress_tracking cpt
            JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
            WHERE cpt.blotter_case_id = %s
              AND UPPER(t.case_progress_type_name) IN ('HEARING HELD','CONCILIATION HELD')
            LIMIT 1
        """, [case_id]))

def hearings_held(case_id: int) -> int:
    """Count hearings held for a case"""
    return int(one_val("""
        SELECT COUNT(*) 
        FROM case_progress_tracking cpt
        JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
        WHERE cpt.blotter_case_id = %s
          AND UPPER(t.case_progress_type_name) = 'HEARING HELD'
    """, [case_id]) or 0)

def hearing_gate(case_id: int) -> Dict[str, Any]:
    """Hearing gate logic"""
    from .all_helpers import _hearing_gate
    return _hearing_gate(case_id)

def prefill_minimal_for_case(case_id: int) -> Dict[str, str]:
    """Get minimal prefill data for a case"""
    # Implementation would mirror lupon_mem functionality
    return {}

def create_and_submit_form_from_prefill(case_id: int, form_code: str, 
                                      prefill: Optional[Dict] = None) -> Optional[int]:
    """Create and submit form with prefill data"""
    # Implementation would mirror lupon_mem functionality
    return None

def list_case_photos(case_id: int) -> List[Dict]:
    """List case photos"""
    # Implementation would mirror lupon_mem functionality
    return []

def list_mediation_photos(case_id: int, submission_id: Optional[int] = None) -> List[Dict]:
    """List mediation photos"""
    # Implementation would mirror lupon_mem functionality
    return []

def get_person_mobile_number(person_id: int) -> Optional[str]:
    """Get person's mobile number"""
    return one_val("""
        SELECT mobile_number
        FROM person
        WHERE person_id = %s
    """, [person_id])

def slice_until_code(fields_with_values: List[Tuple], stop_code: Optional[str]) -> List[Tuple]:
    """Slice fields until a specific code"""
    if not stop_code:
        return fields_with_values
    
    stop_code_lower = stop_code.lower()
    result = []
    
    for item in fields_with_values:
        result.append(item)
        if len(item) > 6 and item[6] and item[6].lower() == stop_code_lower:
            break
    
    return result