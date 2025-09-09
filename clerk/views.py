# clerk/views.py
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import Http404
from postgrest.exceptions import APIError  # ⬅️ catch Supabase errors

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase
from .forms import SearchVerificationRequest

STATUS_APPROVED = 3
STATUS_REJECTED = 4
STATUS_DECLINE  = 7

@session_login_required
@role_required("Barangay Clerk")
@nocache
def review_approve(request):
    auth = request.session.get("auth")
    profile = request.person_profile

    form = SearchVerificationRequest(request.GET or None)  # use GET so pagination keeps the query
    search = (form.cleaned_data.get("search") if form.is_valid() else "") if request.GET else ""

    resp = supabase.rpc("get_id_validation_requests", {}).execute()
    rows = resp.data or []

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
def person_submission_dets(request, req_id: int):
    # Main details
    resp = supabase.rpc("get_details", {"p_person_id": req_id}).execute()
    data = resp.data or []
    if not data:
        raise Http404("Details not found.")
    person = data[0]

    # 🔎 Also get the latest status from your list RPC so we can guard UI/actions
    status_row = None
    try:
        sresp = supabase.rpc("get_id_validation_requests", {}).execute()
        srows = sresp.data or []
        status_row = next((r for r in srows if r.get("requester_person_id") == req_id), None)
    except APIError:
        status_row = None

    if status_row:
        person["latest_status"] = "APPROVED"
        person["latest_remarks"] = status_row.get("latest_remarks")
        person["approved_date"] = status_row.get("approved_date")

    return render(request, "clerk/resident/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "person": person,
    })


def _rpc_approve_person_by_clerk(request, person_id: int, status_id: int, remarks: str | None):
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id")
    if not staff_id:
        raise Http404("Staff not found in session.")

    payload = {
        "p_clerk_staff_id": staff_id,
        "p_person_id": person_id,
        "p_status_id": status_id,
        "p_remarks": remarks,
    }

    # Wrap to convert APIError into a friendly message for the caller.
    try:
        return supabase.rpc("approve_person_by_clerk", payload).execute()
    except APIError as e:
        # e.message is already a dict from PostgREST: {'message': '...', 'code': 'P6026', ...}
        msg = ""
        try:
            msg = e.message.get("message")  # type: ignore[attr-defined]
        except Exception:
            msg = str(e)
        # Re-raise with a clean error message so callers can decide UX
        raise APIError({"message": msg or "Update failed."})


@session_login_required
@role_required("Barangay Clerk")
@nocache
def approve_request(request, req_id: int):
    if request.method != "POST":
        raise Http404()

    try:
        _rpc_approve_person_by_clerk(request, req_id, STATUS_APPROVED, None)
        messages.success(request, "Request approved.")
    except APIError as e:
        # e.message was normalized in helper above
        try:
            messages.warning(request, e.message.get("message"))  # type: ignore[attr-defined]
        except Exception:
            messages.warning(request, "This request cannot be approved.")

    return redirect("clerk:person_details", req_id=req_id)


@session_login_required
@role_required("Barangay Clerk")
@nocache
def decision_request(request, req_id: int):
    if request.method != "POST":
        raise Http404()

    action = (request.POST.get("action") or "").lower()
    remarks = (request.POST.get("remarks") or "").strip()

    if action not in ("reject", "decline"):
        messages.error(request, "Invalid action.")
        return redirect("clerk:person_details", req_id=req_id)

    if not remarks:
        messages.error(request, "Remarks are required.")
        return redirect("clerk:person_details", req_id=req_id)

    status_id = STATUS_REJECTED if action == "reject" else STATUS_DECLINE

    try:
        _rpc_approve_person_by_clerk(request, req_id, status_id, remarks)
        messages.success(
            request,
            f"Request marked as {'Rejected' if status_id==STATUS_REJECTED else 'Declined'}."
        )
    except APIError as e:
        try:
            messages.warning(request, e.message.get("message"))  # type: ignore[attr-defined]
        except Exception:
            messages.warning(request, "This request cannot be updated right now.")

    return redirect("clerk:person_details", req_id=req_id)
