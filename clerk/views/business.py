from __future__ import annotations
from django.shortcuts import render
from django.core.paginator import Paginator
from django.views.decorators.cache import never_cache as nocache  # or import your nocache if different
from django.http import Http404, HttpRequest
from authentication.guards import session_login_required, role_required
from authentication.supabase_client import supabase

from clerk.forms import (
    SearchBusinessOwner, BusinessOwnerInfo, BusinessDetails, BusinessFilters
)

from .shared import (
    CLERK_ROLE, _auth_role_name, _auth_staff_id
)

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner(request: HttpRequest):
    user_role = _auth_role_name(request)
    return render(
        request,
        "business/business_owner.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner",
            "page_title": "Business Owner",
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner_resident(request: HttpRequest):
    user_role = _auth_role_name(request)
    form = SearchBusinessOwner()
    return render(
        request,
        "business/business_owner_resident.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "form": form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner_nonresident(request: HttpRequest):
    user_role = _auth_role_name(request)
    form = BusinessOwnerInfo()
    return render(
        request,
        "business/business_owner_nonres.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "form": form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_details(request: HttpRequest):
    user_role = _auth_role_name(request)
    form = BusinessDetails()
    return render(
        request,
        "business/business_details.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
            "page_title": "Business Information",
            "form": form,
        },
    )

@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_list(request: HttpRequest):
    user_role = _auth_role_name(request)
    form = BusinessFilters()

    rows, rpc_error = [], None

    try:
        resp = supabase.rpc("get_business_summary", {}).execute()
        rows = resp.data or []
    except Exception as e:
        rpc_error = str(e)
        rows = []

    paginator = Paginator(rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_path": f"{user_role} / Business Records",
        "page_title": "Business Records",
        "form": form,
        "rows": rows,
        "rpc_error": rpc_error,
        "page_obj": page_obj,
    }

    return render(
        request,
        "business/business_list.html",
        context,
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_information(request: HttpRequest, b_id: int):
    user_role = _auth_role_name(request)

    b_resp = supabase.rpc("get_business_details", {"p_business_id" : b_id}).execute()
    b_rows = b_resp.data or []
    b = b_rows[0] if b_rows else None

    raw_days = str(b.get("operating_days") or "").strip()
    operating_days_list = [d.strip() for d in raw_days.split(",") if d.strip()] if raw_days else []
    b["operating_days_list"] = operating_days_list

    owner = None
    owner_id = b.get("owner_person_id") or None

    if owner_id:
        p_resp = supabase.rpc("get_details", {"p_person_id" : owner_id}).execute()
        p_rows = p_resp.data or []
        owner = p_rows[0] if p_rows else None

    if not b:
        raise Http404(f"Business {b_id} not found.")

    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {b_id}",
            "page_title": f"Business Details : {b_id}",
            "b": b,
            "owner" : owner,
        },
    )