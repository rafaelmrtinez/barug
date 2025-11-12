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
    case_state_name = (request.POST.get("case_state") or "").strip()
    
    if not case_state_name:
        messages.error(request, "Please select a case state.")
        return redirect("lupon_mem:case_detail", case_id=case_id)

    try:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE blotter_case SET case_state_id = (SELECT case_state_id FROM case_state WHERE case_state_name = %s) WHERE blotter_case_id = %s",
                [case_state_name, case_id]
            )
        messages.success(request, f"Case state updated to {case_state_name}.")
    except Exception as e:
        messages.error(request, f"Failed to update case state: {e}")

    return redirect("lupon_mem:case_detail", case_id=case_id)