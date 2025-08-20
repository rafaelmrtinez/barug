from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from .forms import SearchVerificationRequest
from common.decorators import staff_login_required
from django.conf import settings
from supabase_client import supabase
import requests

user_fullname = 'lname fname mname suffix'
user_role = 'Clerk'
user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.

API_BASE_URL = f"{settings.TESTING_URL_USED}/api/clerk"

@staff_login_required
def review_approve(request):
    pending = []
    paginator = Paginator(pending, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = SearchVerificationRequest()

    return render(request, "resident/review_approve.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form' : form,
    })


# views.py
from django.shortcuts import render
from rest_framework.test import APIRequestFactory
from .api_views import GetIDValidationRequestDetailAPIView


def person_submission_dets(request, req_id):
    try:
        # Call the Supabase function with the specific person_id
        rpc = supabase.rpc("get_details", {"p_person_id": req_id}).execute()

        if not rpc.data:
            request_data = {"error": f"No record found for person_id={req_id}"}
        else:
            # Supabase RPC returns a list, get the first item
            request_data = rpc.data[0]

        # Debug: print the data in console
        print("Fetched request data:", request_data)

    except Exception as e:
        # More graceful error handling
        err_msg = str(e)
        if hasattr(e, "args") and e.args:
            first = e.args[0]
            if isinstance(first, dict) and "message" in first:
                err_msg = first["message"]
        print("Error fetching data:", err_msg)
        request_data = {"error": err_msg}

    return render(request, "clerk/resident/person_submission_dets.html", {
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "user_role_template": user_role_template,
        "req_id": req_id,
        "request_data": request_data,
    })
