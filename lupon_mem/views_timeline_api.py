from django.http import JsonResponse
from django.db import connection
from django.core.serializers.json import DjangoJSONEncoder
from authentication.guards import session_login_required, role_required

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_timeline_api(request, case_id: int):
    try:
        with connection.cursor() as cur:
            # Get state and settlement changes
            cur.execute("""
                SELECT 
                    blotter_case_id,
                    changed_at AT TIME ZONE 'Asia/Manila' as changed_at_raw,
                    TO_CHAR(changed_at AT TIME ZONE 'Asia/Manila', 'Month DD, YYYY') as changed_at_date_pretty,
                    TO_CHAR(changed_at AT TIME ZONE 'Asia/Manila', 'HH12:MI AM') as changed_at_time_pretty,
                    transition_kind,
                    old_state,
                    new_state,
                    remarks,
                    changed_by_id,
                    changed_by_staff_code,
                    changed_by_person_id,
                    changed_by_name
                FROM case_state_history
                WHERE blotter_case_id = %s
                ORDER BY changed_at DESC
            """, [case_id])
            columns = [col[0] for col in cur.description]
            rows = cur.fetchall()
            timeline = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(timeline, safe=False, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)