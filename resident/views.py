from __future__ import annotations

from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import ResidentProfileform
from .forms import HouseholdProfileForm
from .forms import FamilyProfileForm

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Clerk'

user_role_template = user_role.lower().replace(' ', '_')

# resident/views.py

from typing import Any, Dict, List

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.html import escape

from authentication.supabase_client import supabase  # uses your service key client


# ---- small helpers -----------------------------------------------------------

STATUS_UI = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}

def _person_id(request) -> int | None:
    # Adjust to your middleware/session shape
    return (
        getattr(getattr(request, "profile", None), "person_id", None)
        or request.session.get("person_id")
    )

def _titleize(code: str | None) -> str:
    if not code:
        return ""
    return code.replace("_", " ").title()


# ---- list view ---------------------------------------------------------------

def docreq_history(request):
    """Resident's own history page (list)."""
    person_id = 4
    if not person_id:
        messages.error(request, "No resident profile bound to this session.")
        return redirect("/")

    q = (request.GET.get("q") or "").strip() or None
    page = max(int(request.GET.get("page", "1") or 1), 1)
    page_size = 20
    offset = (page - 1) * page_size

    res = supabase.rpc(
        "search_requests_for_resident",
        {"p_person_id": 4, "p_q": q, "p_limit": page_size, "p_offset": offset},
    ).execute()

    rows: List[Dict[str, Any]] = []
    if getattr(res, "error", None):
        messages.error(request, f"Supabase error: {escape(res.error.message)}")
    else:
        rows = res.data or []

    # annotate rows for UI (status badge + pretty purpose names)
    for r in rows:
        ui = STATUS_UI.get(r.get("status")) or {"label": r.get("status") or "—", "cls": "badge text-bg-secondary"}
        r["status_ui"] = ui
        r["purposes_display"] = [_titleize(p) for p in (r.get("purposes") or [])]

    ctx = {
        "rows": rows,
        "q": q or "",
        "page": page,
        "has_more": len(rows) == page_size,
    }
    return render(request, "resident/docreq_history.html", ctx)


# ---- detail/receipt view -----------------------------------------------------

def docreq_detail(request, doc_request_id: int):
    """One request detail/receipt page."""
    person_id = _person_id(request)

    res = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Supabase error: {escape(res.error.message)}")
        return redirect("resident:docreq_history")

    data: Dict[str, Any] = res.data or {}
    header = data.get("header") or {}
    lines  = data.get("lines") or []
    pay    = data.get("payments") or {}
    tl     = data.get("timeline") or []

    # simple authorization guard (resident can see only own/for them)
    if person_id:
        if header and header.get("requested_by_id") != person_id and header.get("on_behalf_id") != person_id:
            return HttpResponseForbidden("You are not allowed to view this request.")

    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}

    # prettify lines (purpose)
    for l in lines:
        l["purpose_display"] = _titleize(l.get("purpose_code"))

    ctx = {
        "header": header,
        "status_ui": ui,
        "lines": lines,
        "payments": pay,
        "timeline": tl,
    }
    return render(request, "resident/docreq_detail.html", ctx)


# Create your views here.
def register_resident(request):
    return render(request, "resident_profiling/register_resident.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident',
        'page_title' : 'Register Resident',
        'user_role_template' : user_role_template,
    })

def personal_info(request):
    form = ResidentProfileform()

    return render(request, "person/personal_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Personal Information',
        'page_title' : 'Personal Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def socioeconomic_info(request):
    form = ResidentProfileform()

    return render(request, "person/socioeconomic_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Socioeconomic Information',
        'page_title' : 'Socioeconomic Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def supporting_documents(request):
    form = ResidentProfileform()

    return render(request, "person/supporting_documents.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Supporting Documents',
        'page_title' : 'Supporting Documents',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def review_info(request):
    return render(request, "resident_profiling/review_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f"{user_role} / Resident Management / Register Resident / Review Resident's Information" ,
        'page_title' : "Review Resident's Information",
        'user_role_template' : user_role_template,
    })

def resident_records(request):
    # item_list = MyModel.objects.all()
    # paginator = Paginator(item_list, 10)

    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)

    return render(request, 'resident_profiling/resident_records.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        # 'page_obj' : page_obj,
    })

def resident_record(request, res_id):
    form = ResidentProfileform()

    for field in form.fields.values():
        field.disabled = True
        field.widget.attrs['class'] = 'form-control editable-field'

    return render(request, 'resident_profiling/resident_record.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records / Resident : {res_id}',
        'page_title' : f'Resident : {res_id}',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def household_info(request: HttpRequest) -> HttpResponse:
    form = HouseholdProfileForm()
    user_role=request.session.get('auth').get('role_name')
    user_role_template=user_role.lower().replace(' ', '_')
    return render(request, 'household_profiling/household_info.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def family_info(request: HttpRequest) -> HttpResponse:
    form = FamilyProfileForm()
    user_role=request.session.get('auth').get('role_name')
    user_role_template=user_role.lower().replace(' ', '_')
    return render(request, 'household_profiling/family_info.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        'form' : form,
    })