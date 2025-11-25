from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import connection
from authentication.guards import session_login_required, role_required

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def update_case_state(request, case_id: int):
    from lupon_mem.utils.logging import blotter_log_event
    case_state_name = (request.POST.get("case_state") or "").strip()
    remarks = (request.POST.get("remarks") or "").strip() or None
    staff_id = (request.session.get("auth") or {}).get("staff_id")
    
    if not case_state_name:
        messages.error(request, "Please select a case state.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            # Get old case state and case details
            cur.execute(
                "SELECT cs.case_state_name, bc.blotter_case_num, bc.blotter_case_name FROM blotter_case bc LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id WHERE bc.blotter_case_id = %s",
                [case_id]
            )
            row = cur.fetchone()
            old_state = row[0] if row else None
            case_num = row[1] if row else None
            case_name = row[2] if row else None
            
            # Get staff name
            staff_name = None
            if staff_id:
                cur.execute(
                    "SELECT TRIM(CONCAT_WS(' ', p.first_name, NULLIF(SUBSTRING(COALESCE(p.middle_name, '') FROM 1 FOR 1) || '.', '.'), p.last_name, NULLIF(p.suffix, ''))) FROM staff s JOIN person p ON p.person_id = s.person_id WHERE s.staff_id = %s",
                    [staff_id]
                )
                staff_row = cur.fetchone()
                staff_name = staff_row[0] if staff_row else None
            
            # Update case state
            cur.execute(
                "UPDATE blotter_case SET case_state_id = (SELECT case_state_id FROM case_state WHERE case_state_name = %s), updated_at = now() WHERE blotter_case_id = %s",
                [case_state_name, case_id]
            )
            
            # Build message
            message = f"{staff_name or f'Staff ID {staff_id}'} updated the case state to {case_state_name} for Case {case_num or f'#{case_id}'} – {case_name or 'Unnamed Case'}"
            if remarks:
                message += f" (remarks: {remarks})"
            
            # Log event
            blotter_log_event(
                action="UPDATE_CASE_STATE",
                table_affected="blotter_case",
                record_affected_id=case_id,
                details=message,
                performer_staff_id=staff_id,
                field_changed="case_state",
                old_value=old_state,
                new_value=case_state_name
            )
            
        messages.success(request, f"Case state updated to {case_state_name}.")
    except Exception as e:
        messages.error(request, f"Failed to update case state: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)