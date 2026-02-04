# lupon_mem/services/kp_notification_service.py
from django.db import connection
from notifications.service import notify_user
import logging

logger = logging.getLogger(__name__)

def notify_kp_submission(submission_id: int, case_id: int, form_code: str):
    """
    Send in-app notifications when a KP form is submitted.
    Notifies all Lupon members and relevant staff about the submission.
    """
    try:
        # Get case details
        with connection.cursor() as cur:
            cur.execute("""
                SELECT bc.blotter_case_num, bc.blotter_case_name,
                       COALESCE(ct.complaint_title_name, '') as complaint_title
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            
            case_row = cur.fetchone()
            if not case_row:
                logger.warning(f"Case {case_id} not found for KP submission notification")
                return
            
            case_num, case_name, complaint_title = case_row
            
            # Get form name
            cur.execute("""
                SELECT form_name FROM kp_form 
                WHERE UPPER(form_code) = UPPER(%s)
            """, [form_code])
            
            form_row = cur.fetchone()
            form_name = form_row[0] if form_row else form_code
            
            # Get all Lupon members and relevant staff
            cur.execute("""
                SELECT s.staff_id, p.person_id, r.role_name,
                       TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) as full_name
                FROM staff s
                JOIN person p ON p.person_id = s.person_id
                JOIN rolee r ON r.role_id = s.role_id
                WHERE r.role_name IN (
                    'BARANGAY LUPON MEMBER',
                    'BARANGAY LUPON PRESIDENT', 
                    'BARANGAY CAPTAIN',
                    'BARANGAY SECRETARY'
                )
            """)
            
            staff_members = cur.fetchall()
            
        # Create notification message
        title = f"New {form_code} Submission"
        body = f"{form_name} has been submitted for Case #{case_num}: {case_name or complaint_title}"
        deep_link = f"/(residentmodals)/(brgycases)/brgycasesdetails/{case_id}"
        
        # Send notifications to all relevant staff
        for staff_id, person_id, role_name, full_name in staff_members:
            try:
                notify_user(
                    user_type_id=2,  # Staff user type
                    person_id=None,
                    staff_id=staff_id,
                    title=title,
                    body=body,
                    deep_link=deep_link
                )
                logger.info(f"Sent KP submission notification to {full_name} ({role_name})")
            except Exception as e:
                logger.error(f"Failed to send notification to staff {staff_id}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to send KP submission notifications: {e}")

def notify_case_progress(case_id: int, progress_type: str, remarks: str = None):
    """
    Send notifications for case progress updates (hearing held, settlement, etc.)
    """
    try:
        with connection.cursor() as cur:
            # Get case details
            cur.execute("""
                SELECT bc.blotter_case_num, bc.blotter_case_name,
                       COALESCE(ct.complaint_title_name, '') as complaint_title
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                WHERE bc.blotter_case_id = %s
            """, [case_id])
            
            case_row = cur.fetchone()
            if not case_row:
                return
                
            case_num, case_name, complaint_title = case_row
            
            # Get parties involved in the case
            cur.execute("""
                SELECT DISTINCT p.person_id, 
                       TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) as full_name,
                       'COMPLAINANT' as party_type
                FROM complainant_case cc
                JOIN person p ON p.person_id = cc.person_id
                WHERE cc.blotter_case_id = %s
                
                UNION ALL
                
                SELECT DISTINCT p.person_id,
                       TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.last_name, '')) as full_name,
                       'RESPONDENT' as party_type
                FROM respondent_case rc
                JOIN person p ON p.person_id = rc.person_id
                WHERE rc.blotter_case_id = %s
            """, [case_id, case_id])
            
            parties = cur.fetchall()
            
        # Create notification message
        title = f"Case Update: {progress_type}"
        body = f"Case #{case_num}: {case_name or complaint_title} - {progress_type}"
        if remarks:
            body += f" - {remarks}"
        deep_link = f"/(residentmodals)/(brgycases)/brgycasesdetails/{case_id}"
        
        # Send notifications to parties involved
        for person_id, full_name, party_type in parties:
            try:
                notify_user(
                    user_type_id=1,  # Person user type
                    person_id=person_id,
                    staff_id=None,
                    title=title,
                    body=body,
                    deep_link=deep_link
                )
                logger.info(f"Sent case progress notification to {full_name} ({party_type})")
            except Exception as e:
                logger.error(f"Failed to send notification to person {person_id}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to send case progress notifications: {e}")