# Test what data exists for case 22
from django.http import JsonResponse
from django.db import connection
from lupon_mem.services.case_forms_utils import fetch_all_case_forms_data

def test_case_22_data(request):
    case_id = 22
    
    # Check form 41's form_code
    with connection.cursor() as cur:
        cur.execute("SELECT form_id, form_code, form_name FROM kp_form WHERE form_id = 41")
        form_info = cur.fetchone()
    
    # Get all forms data
    forms_data = fetch_all_case_forms_data(case_id)
    
    return JsonResponse({
        "form_41_info": {
            "form_id": form_info[0] if form_info else None,
            "form_code": form_info[1] if form_info else None,
            "form_name": form_info[2] if form_info else None,
        },
        "case_22_data": forms_data
    })
