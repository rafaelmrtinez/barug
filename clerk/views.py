# clerk/views.py
from django.shortcuts import render
from django.core.paginator import Paginator
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from .forms import SearchVerificationRequest
from authentication.supabase_client import supabase

@session_login_required
@role_required("Barangay Clerk")
@nocache
def review_approve(request):
    auth = request.session.get("auth")
    profile = request.person_profile

    form = SearchVerificationRequest(request.POST or None)
    search = ""
    if request.method == "POST" and form.is_valid():
        search = form.cleaned_data.get("search") or ""

    # 🔽 Call your Postgres function
    # If you later add server-side filtering, pass named args here (e.g., {"p_search": search})
    resp = supabase.rpc("get_id_validation_requests", {}).execute()
    rows = resp.data or []

    # very simple in-Python filter for now (optional)
    if search:
        q = search.lower().strip()
        rows = [
            r for r in rows
            if q in f"{r.get('requester_first_name','')} {r.get('requester_last_name','')}".lower()
            or q in (r.get("latest_status","") or "").lower()
        ]

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "resident/review_approve.html", {
        "page_path": "Barangay Clerk / Account Verification",
        "page_title": "Account Verification",
        "page_obj": page_obj,
        "form": form,
        "profile": profile,
        "auth": auth,
    })



@session_login_required
@role_required("Barangay Clerk")
@nocache
def person_submission_dets(request, req_id):
    return render(request, "person/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
    })
