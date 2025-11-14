# lupon_pres/services/all_helpers.py
"""
All helper functions for lupon_pres - mirrors lupon_mem.services.all_helpers
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from django.db import connection
import logging

log = logging.getLogger(__name__)

def _hearing_gate(case_id: int) -> Dict[str, Any]:
    """
    Hearing gate logic - mirrors lupon_mem functionality
    """
    try:
        with connection.cursor() as cur:
            # Check if there are any outstanding notices
            cur.execute("""
                SELECT COUNT(*) > 0 as has_notices
                FROM blotter_kp_submission s
                JOIN kp_form f ON f.form_id = s.form_id
                WHERE s.blotter_case_id = %s
                  AND UPPER(f.form_code) IN ('KP-8', 'KP-12')
                  AND UPPER(s.status) = 'SUBMITTED'
            """, [case_id])
            
            has_notices = cur.fetchone()[0] if cur.rowcount else False
            
            # Check hearings held
            cur.execute("""
                SELECT COUNT(*) as hearings_held
                FROM case_progress_tracking cpt
                JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                WHERE cpt.blotter_case_id = %s
                  AND UPPER(t.case_progress_type_name) IN ('HEARING HELD', 'CONCILIATION HELD')
            """, [case_id])
            
            hearings_held = cur.fetchone()[0] if cur.rowcount else 0
            
        return {
            "can_issue_notice": True,
            "latest_notice_outstanding": has_notices,
            "hearings_held": hearings_held,
            "reason": ""
        }
        
    except Exception as e:
        log.exception("Error in _hearing_gate")
        return {
            "can_issue_notice": False,
            "latest_notice_outstanding": False,
            "hearings_held": 0,
            "reason": "System error"
        }

def hearing_gate(case_id: int) -> Dict[str, Any]:
    """Public interface for hearing gate"""
    return _hearing_gate(case_id)