# lupon_mem/services/hearings.py
from __future__ import annotations
from typing import Optional, Tuple
from django.utils import timezone
from ..db import q, q1, exec_only

def get_case_num(case_id: int) -> str:
    row = q1("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id=%s", (case_id,))
    return row[0] if row else f"{case_id}"

def mark_mediation_held(
    *, case_id: int, submission_id: Optional[int],
    compl_attended: bool, resp_attended: bool,
    settlement: Optional[str], held_remarks: Optional[str]
) -> Tuple[bool, str]:
    """
    Mark mediation as held using the hearing_attendance table.
    """
    from django.db import connection
    
    try:
        with connection.cursor() as cur:
            # Get source code from submission
            source_code = 'KP-8'  # Default for mediation
            if submission_id:
                cur.execute("""
                    SELECT UPPER(kf.form_code)
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    WHERE s.submission_id = %s
                """, [submission_id])
                row = cur.fetchone()
                if row:
                    source_code = row[0]
            
            # Insert hearing_attendance
            cur.execute("""
                INSERT INTO hearing_attendance 
                (blotter_case_id, notice_submission_id, source_code, held_at, 
                 complainant_attended, respondent_attended, settlement_outcome, remarks)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)
            """, [case_id, submission_id or 0, source_code, compl_attended, resp_attended, settlement, held_remarks])
            
            # Add progress tracking entry
            cur.execute("""
                INSERT INTO case_progress_tracking 
                (blotter_case_id, case_progress_type_id, remarks, date_processed)
                SELECT %s, cpt.case_progress_type_id, %s, NOW()
                FROM case_progress_type cpt
                WHERE UPPER(cpt.case_progress_type_name) = 'HEARING HELD'
                LIMIT 1
            """, [case_id, held_remarks])
        
        return True, "Mediation marked as held."
    except Exception as e:
        return False, f"Failed to mark mediation as held: {str(e)}"

def mark_conciliation_held(
    *, case_id: int, submission_id: Optional[int],
    compl_attended: bool, resp_attended: bool,
    settlement: Optional[str], held_remarks: Optional[str]
) -> Tuple[bool, str]:
    """
    Mark conciliation as held using the hearing_attendance table.
    """
    from django.db import connection
    
    try:
        with connection.cursor() as cur:
            # Get source code from submission
            source_code = 'KP-12'  # Default for conciliation
            if submission_id:
                cur.execute("""
                    SELECT UPPER(kf.form_code)
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    WHERE s.submission_id = %s
                """, [submission_id])
                row = cur.fetchone()
                if row:
                    source_code = row[0]
            
            # Insert hearing_attendance
            cur.execute("""
                INSERT INTO hearing_attendance 
                (blotter_case_id, notice_submission_id, source_code, held_at, 
                 complainant_attended, respondent_attended, settlement_outcome, remarks)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)
            """, [case_id, submission_id or 0, source_code, compl_attended, resp_attended, settlement, held_remarks])
            
            # Add progress tracking entry
            cur.execute("""
                INSERT INTO case_progress_tracking 
                (blotter_case_id, case_progress_type_id, remarks, date_processed)
                SELECT %s, cpt.case_progress_type_id, %s, NOW()
                FROM case_progress_type cpt
                WHERE UPPER(cpt.case_progress_type_name) = 'CONCILIATION HELD'
                LIMIT 1
            """, [case_id, held_remarks])
        
        return True, "Conciliation marked as held."
    except Exception as e:
        return False, f"Failed to mark conciliation as held: {str(e)}"
