from django.shortcuts import render
from django.core.paginator import Paginator
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from .forms import SearchVerificationRequest


@session_login_required
@role_required("Barangay Clerk")
@nocache
def review_approve(request):
    # Debug: print session auth details in server logs  
    auth = request.session.get("auth")
    print("🔐 Session auth payload:", auth)
    profile = request.person_profile  # already attached
    # TODO: Replace this with your actual Supabase query for pending verifications
    pending = []

    paginator = Paginator(pending, 10)  # paginate 10 per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    form = SearchVerificationRequest()

    return render(request, "resident/review_approve.html", {
        "page_path": "Barangay Clerk / Account Verification",
        "page_title": "Account Verification",
        "page_obj": page_obj,
        "form": form,
        "profile": profile,    # raw profile if you want to access other fields
        "auth": auth,   # also pass to template if you want
    })



@session_login_required
@role_required("Barangay Clerk")
@nocache
def person_submission_dets(request, req_id):
    return render(request, "person/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
    })
