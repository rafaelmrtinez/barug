# lupon_pres/services/timeline.py
"""
Timeline service for lupon_pres - mirrors lupon_mem.services.timeline
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from django.db import connection
import logging

log = logging.getLogger(__name__)

def get_case_timeline(case_id: int) -> Dict[str, Any]:
    """
    Get case timeline data - mirrors lupon_mem functionality
    """
    try:
        with connection.cursor() as cur:
            # Get case header
            cur.execute("""
                SELECT 
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.date_filed,
                    COALESCE(bc.blotter_case_name, '') as case_name,
                    COALESCE(ct.complaint_title_name, '') as complaint_title,
                    COALESCE(cn.case_name, '') as case_nature
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            
            header = cur.fetchone()
            if not header:
                return {"header": None, "timeline": []}
            
            # Get timeline events
            cur.execute("""
                SELECT 
                    cpt.date_processed,
                    t.case_progress_type_name,
                    cpt.remarks,
                    COALESCE(s.staff_name, '') as processed_by
                FROM case_progress_tracking cpt
                JOIN case_progress_type t ON t.case_progress_type_id = cpt.case_progress_type_id
                LEFT JOIN staff s ON s.staff_id = cpt.processed_by_id
                WHERE cpt.blotter_case_id = %s
                ORDER BY cpt.date_processed DESC
            """, [case_id])
            
            timeline = [
                {
                    "date": row[0],
                    "event": row[1],
                    "remarks": row[2],
                    "processed_by": row[3]
                }
                for row in cur.fetchall()
            ]
            
        return {
            "header": {
                "case_id": header[0],
                "case_num": header[1],
                "date_filed": header[2],
                "case_name": header[3],
                "complaint_title": header[4],
                "case_nature": header[5]
            },
            "timeline": timeline
        }
        
    except Exception as e:
        log.exception("Error in get_case_timeline")
        return {"header": None, "timeline": []}