# lupon_mem/views_hearings.py
from __future__ import annotations
from django.shortcuts import redirect
from django.http import HttpRequest
from authentication.guards import session_login_required, role_required
from .views_shared import LUPON_ROLES, _hearing_gate
from django.views.decorators.http import require_POST
# (This module is a stub for future hearing-specific POST actions like “mark held”.
#  Your current hearing logic lives inside helper gates and KP-16 submit hook.)
#  Keeping it minimal now to avoid duplicating code.

@session_login_required
@role_required(*LUPON_ROLES)
@require_POST
def reschedule_hearing(request: HttpRequest, case_id: int):
    """Reschedule a hearing using the fn_reschedule_hearing function"""
    from django.db import connection
    from django.http import JsonResponse
    from notifications.service import notify_user, PERSON
    
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    
    submission_id = request.POST.get("submission_id")
    new_date = request.POST.get("new_date")
    new_time = request.POST.get("new_time")
    remarks = request.POST.get("remarks", "").strip()
    
    if not submission_id or not new_date or not new_time:
        return JsonResponse({"success": False, "error": "Missing required fields for rescheduling."})
    
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT * FROM fn_reschedule_hearing(%s, %s, %s, %s, %s)",
                [int(submission_id), new_date, new_time, remarks or None, staff_id]
            )
            result = cur.fetchone()
            
            if result and result[0]:  # success column
                # Get case number for notification
                try:
                    cur.execute("SELECT blotter_case_num FROM blotter_case WHERE blotter_case_id = %s", [case_id])
                    case_row = cur.fetchone()
                    case_num = case_row[0] if case_row else str(case_id)
                except Exception:
                    case_num = str(case_id)
                
                # Format time with AM/PM
                from datetime import datetime
                try:
                    time_obj = datetime.strptime(new_time, "%H:%M")
                    formatted_time = time_obj.strftime("%I:%M %p")
                except Exception:
                    formatted_time = new_time
                
                # Send notifications to case parties
                try:
                    from notifications import repo
                    for role, person_id in repo.case_party_person_ids(case_id):
                        try:
                            notify_user(
                                user_type_id=PERSON,
                                person_id=person_id,
                                staff_id=None,
                                title=f"Hearing Rescheduled — Case {case_num}",
                                body=f"Your hearing for Case #{case_num} has been rescheduled to {new_date} at {formatted_time}. Please make sure to attend.",
                                deep_link=f"/(residentmodals)/(brgycases)/brgycasesdetails/{case_id}"
                            )
                        except Exception as e:
                            print(f"Failed to notify person {person_id}: {e}")
                except Exception as e:
                    print(f"Failed to send notifications: {e}")
                
                return JsonResponse({"success": True, "message": f"Hearing successfully rescheduled to {new_date} {formatted_time}. You can download the updated KP-8 and KP-9 forms as they have been automatically updated with the new schedule."})
            else:
                return JsonResponse({"success": False, "error": "Failed to reschedule hearing."})
                
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error rescheduling hearing: {str(e)}"})