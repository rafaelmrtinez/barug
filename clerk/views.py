# clerk/views.py
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.conf import settings

from src.infra.authentication.claims import Claims
from .forms import SearchVerificationRequest
from common.decorators import staff_login_required, staff_positions_required
from supabase_client import supabase

from django.shortcuts import render
from rest_framework.test import APIRequestFactory
from .api_views import GetIDValidationRequestDetailAPIView

# --- Static UI labels (replace with real data as needed) ---
user_fullname = 'lname fname mname suffix'
user_role = 'Clerk'
user_role_template = user_role.lower().replace(' ', '_')

API_BASE_URL = f"{settings.TESTING_URL_USED}/api/clerk"

# =========================
# Views
# =========================

@staff_positions_required("BARANGAY CLERK")
def review_approve(request):
    pending = []  # populate as needed
    paginator = Paginator(pending, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    user_payload = request.session.get("user", {})
    user_fullname = user_payload.get("user_fullname")
    user_role = user_payload.get("position")
    form = SearchVerificationRequest()

    return render(request, "resident/review_approve.html", {
        "api_base_url": API_BASE_URL,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'page_obj': page_obj,
        'form': form,
    })



@staff_login_required
def person_submission_dets(request, req_id):
    verify_req_id = request.GET.get("verify_req_id")  # from list page link
    try:
        rpc = supabase.rpc("get_details", {"p_person_id": req_id}).execute()
        request_data = rpc.data[0] if rpc.data else {"error": f"No record found for person_id={req_id}"}
    except Exception as e:
        err_msg = e.args[0].get("message") if getattr(e, "args", None) and isinstance(e.args[0], dict) else str(e)
        request_data = {"error": err_msg}

    # prefer verify_req_id from URL; else fall back to whatever your details has
    request_id = verify_req_id or request_data.get("request_id") or req_id

    user_payload = request.session.get("user", {})
    clerk_staff_id = user_payload.get("user_id")

    return render(request, "clerk/resident/person_submission_dets.html", {
        "req_id": req_id,
        "request_id": request_id,       # <-- this powers the Approve call
        "request_data": request_data,
        "api_base_url": API_BASE_URL,
        "person_id": req_id,
        "clerk_staff_id": clerk_staff_id,
        "user_fullname": user_fullname,
        "user_role": user_role,
        "page_path": f"{user_role} / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "user_role_template": user_role_template,

        "req_id": req_id,             # the person id you clicked from
        "request_id": request_id,     # ✅ actual request id for the approve/decline endpoint
        "request_data": request_data,

        "api_base_url": API_BASE_URL,
        "person_id": req_id,
        "clerk_staff_id": clerk_staff_id,   # ✅ from session
    })
