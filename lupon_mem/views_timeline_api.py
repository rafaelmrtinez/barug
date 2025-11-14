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
            cur.execute("SELECT * FROM rpc_case_state_timeline(%s)", [case_id])
            columns = [col[0] for col in cur.description]
            rows = cur.fetchall()
            timeline = [dict(zip(columns, row)) for row in rows]
            return JsonResponse(timeline, safe=False, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)