# lupon_pres/services/case_state.py
"""
Case state management for lupon_pres - mirrors lupon_mem.services.case_state
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection
import logging

log = logging.getLogger(__name__)

def close_case(case_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
    """
    Close a case - mirrors lupon_mem functionality
    """
    try:
        with connection.cursor() as cur:
            # Get CLOSED case state ID
            cur.execute("""
                SELECT case_state_id
                FROM case_state
                WHERE UPPER(case_state_name) = 'CLOSED'
                LIMIT 1
            """)
            
            row = cur.fetchone()
            if not row:
                return False, "CLOSED case state not found"
            
            closed_state_id = row[0]
            
            # Update case state
            cur.execute("""
                UPDATE blotter_case
                SET case_state_id = %s
                WHERE blotter_case_id = %s
            """, [closed_state_id, case_id])
            
            # Add progress tracking
            cur.execute("""
                SELECT case_progress_type_id
                FROM case_progress_type
                WHERE UPPER(case_progress_type_name) = 'CASE CLOSED'
                LIMIT 1
            """)
            
            progress_row = cur.fetchone()
            if progress_row:
                cur.execute("""
                    INSERT INTO case_progress_tracking
                        (blotter_case_id, case_progress_type_id, date_processed, remarks)
                    VALUES (%s, %s, NOW(), %s)
                """, [case_id, progress_row[0], reason or "Case closed"])
            
        return True, "Case closed successfully"
        
    except Exception as e:
        log.exception("Error in close_case")
        return False, f"Error: {str(e)}"

def reopen_case(case_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
    """
    Reopen a closed case - mirrors lupon_mem functionality
    """
    try:
        with connection.cursor() as cur:
            # Get OPEN case state ID
            cur.execute("""
                SELECT case_state_id
                FROM case_state
                WHERE UPPER(case_state_name) = 'OPEN'
                LIMIT 1
            """)
            
            row = cur.fetchone()
            if not row:
                return False, "OPEN case state not found"
            
            open_state_id = row[0]
            
            # Update case state
            cur.execute("""
                UPDATE blotter_case
                SET case_state_id = %s
                WHERE blotter_case_id = %s
            """, [open_state_id, case_id])
            
            # Add progress tracking
            cur.execute("""
                SELECT case_progress_type_id
                FROM case_progress_type
                WHERE UPPER(case_progress_type_name) = 'CASE REOPENED'
                LIMIT 1
            """)
            
            progress_row = cur.fetchone()
            if progress_row:
                cur.execute("""
                    INSERT INTO case_progress_tracking
                        (blotter_case_id, case_progress_type_id, date_processed, remarks)
                    VALUES (%s, %s, NOW(), %s)
                """, [case_id, progress_row[0], reason or "Case reopened"])
            
        return True, "Case reopened successfully"
        
    except Exception as e:
        log.exception("Error in reopen_case")
        return False, f"Error: {str(e)}"