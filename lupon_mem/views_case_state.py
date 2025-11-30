from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connection
from authentication.guards import session_login_required, role_required
import logging

logger = logging.getLogger(__name__)
LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def update_case_state(request, case_id: int):
    case_state_name = (request.POST.get("case_state") or "").strip()
    remarks = (request.POST.get("remarks") or "").strip() or None
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    
    logger.info(f"[UPDATE_CASE_STATE] Starting update for case_id={case_id}, state={case_state_name}, staff_id={staff_id}, remarks={remarks}")
    
    if not case_state_name:
        messages.error(request, "Please select a case state.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            # Get current state before update
            cur.execute(
                "SELECT cs.case_state_name FROM blotter_case bc LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            old_state = cur.fetchone()
            old_state_name = old_state[0] if old_state else None
            logger.info(f"[UPDATE_CASE_STATE] Current state: {old_state_name}")
            
            # Call database function to update case state
            logger.info(f"[UPDATE_CASE_STATE] Calling fn_update_case_state({case_id}, {case_state_name}, {staff_id}, {remarks})")
            cur.execute(
                "SELECT fn_update_case_state(%s, %s, %s, %s)",
                [case_id, case_state_name, staff_id, remarks]
            )
            result = cur.fetchone()
            logger.info(f"[UPDATE_CASE_STATE] Function returned: {result}")
            
            # Verify the update
            cur.execute(
                "SELECT cs.case_state_name FROM blotter_case bc LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            new_state = cur.fetchone()
            new_state_name = new_state[0] if new_state else None
            logger.info(f"[UPDATE_CASE_STATE] New state after update: {new_state_name}")
            
            if new_state_name == case_state_name:
                logger.info(f"[UPDATE_CASE_STATE] SUCCESS: State changed from {old_state_name} to {new_state_name}")
                messages.success(request, f"Case state updated to {case_state_name}.")
            else:
                logger.warning(f"[UPDATE_CASE_STATE] WARNING: State did not change. Expected {case_state_name}, got {new_state_name}")
                messages.warning(request, f"Case state update may have failed. Current state: {new_state_name}")
            
    except Exception as e:
        logger.error(f"[UPDATE_CASE_STATE] ERROR: {str(e)}", exc_info=True)
        messages.error(request, f"Failed to update case state: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)