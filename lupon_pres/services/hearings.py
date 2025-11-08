# lupon_pres/services/hearings.py
"""
Hearings service for lupon_pres - mirrors lupon_mem.services.hearings
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection
import logging

log = logging.getLogger(__name__)

def mark_conciliation_held(case_id: int, submission_id: int, 
                          compl_attended: bool, resp_attended: bool,
                          settlement: Optional[str] = None, 
                          held_remarks: Optional[str] = None) -> Tuple[bool, str]:
    """
    Mark conciliation as held - mirrors lupon_mem functionality
    """
    try:
        with connection.cursor() as cur:
            # Get progress type ID for CONCILIATION HELD
            cur.execute("""
                SELECT case_progress_type_id
                FROM case_progress_type
                WHERE UPPER(case_progress_type_name) = 'CONCILIATION HELD'
                LIMIT 1
            """)
            
            row = cur.fetchone()
            if not row:
                return False, "Progress type 'CONCILIATION HELD' not found"
            
            progress_type_id = row[0]
            
            # Insert progress tracking
            cur.execute("""
                INSERT INTO case_progress_tracking
                    (blotter_case_id, case_progress_type_id, date_processed, remarks)
                VALUES (%s, %s, NOW(), %s)
            """, [case_id, progress_type_id, held_remarks or "Conciliation held"])
            
        return True, "Conciliation marked as held successfully"
        
    except Exception as e:
        log.exception("Error in mark_conciliation_held")
        return False, f"Error: {str(e)}"

def get_case_num(case_id: int) -> str:
    """Get case number for a case ID"""
    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT blotter_case_num
                FROM blotter_case
                WHERE blotter_case_id = %s
            """, [case_id])
            
            row = cur.fetchone()
            return row[0] if row else f"Case #{case_id}"
            
    except Exception as e:
        log.exception("Error in get_case_num")
        return f"Case #{case_id}"