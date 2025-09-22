from __future__ import annotations

from typing import Any, Dict, List
import io, os, zipfile, json, re
from datetime import datetime

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils import timezone
from django.conf import settings
from django.views.decorators.http import require_POST

from postgrest.exceptions import APIError

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase

from .forms import SearchVerificationRequest, SearchBusinessOwner, BusinessDetails, BusinessFilters

from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import RequestedDocsFilters

user_fullname = 'lname fname mname suffix'
user_role = 'Barangay Treasurer'
user_role_template = user_role.lower().replace(' ', '_')

# ---- services ----
from .services.requests_service import _fetch_bundle, _set_status
from .services.subject_service import subject_view
from .services.pdf_service import (
    _pdf_templates_dir, _get_all_pdf_field_names, _fill_pdf_with_values,
    _choose_template, _safe_str, _fill_fields_for_line
)
from .services.id_verification_service import (
    fetch_id_verification_requests,
    get_verification_status_for_person,
)

# =========================
# UI helpers / constants
# =========================

STATUS_UI: Dict[str, Dict[str, str]] = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}
CLERK_STATUSES_ALL = ["PAID", "FOR_PRINTING", "RELEASED", "DECLINED"]
CLERK_ROLE = "Barangay Clerk"

def _titleize(s: str | None) -> str:
    return "" if not s else s.replace("_", " ").title()

def _staff_id(request: HttpRequest) -> int | None:
    """Prefer session['auth']['staff_id'] set at login; fallback to profile objects."""
    auth = request.session.get("auth") or {}
    sid = auth.get("staff_id")
    if sid:
        return sid
    prof = getattr(request, "profile", None) or getattr(request, "person_profile", None)
    return getattr(prof, "staff_id", None)

# =========================
# Clerk — Queue / List of document requests
# =========================
@session_login_required
@role_required(CLERK_ROLE)
@nocache
def queue(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None

    statuses = request.GET.getlist("status")
    if not statuses:
        raw = (request.GET.get("status") or "").strip()
        statuses = [s for s in raw.split(",") if s] if raw else CLERK_STATUSES_ALL[:2]

    query = supabase.table("v_doc_request_list_ex").select("*").order("doc_request_id", desc=True)
    if statuses:
        query = query.in_("status", statuses)
    if q:
        array_probe = "{" + q + "}"
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.ov.{array_probe},purposes.ov.{array_probe}")

    res = query.limit(200).execute()
    rows: List[Dict[str, Any]] = res.data or []
    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {"label": r.get("status") or "—", "cls": "badge text-bg-secondary"}
        r["purposes_display"] = [_titleize(p) for p in (r.get("purposes") or [])]
        fn = (r.get("requester_first_name") or r.get("first_name") or "").strip()
        ln = (r.get("requester_last_name") or r.get("last_name") or "").strip()
        full = (r.get("requester_full_name") or r.get("resident_name") or "").strip() or " ".join([fn, ln]).strip()
        r["requester_display"] = full or None
        created_at = r.get("created_at") or r.get("created_ts") or r.get("date_created")
        try:
            r["created_fmt"] = created_at.strftime("%b %d, %Y %H:%M")  # type: ignore
        except Exception:
            r["created_fmt"] = str(created_at)

    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "clerk/queue.html", {
        "page_obj": page_obj, "rows": page_obj.object_list,
        "q": q or "", "statuses": statuses, "statuses_all": CLERK_STATUSES_ALL,
        "active_count": len(statuses),
    })

# =========================
# Clerk — Detail of a document request
# =========================
@session_login_required
@role_required(CLERK_ROLE)
@nocache
def detail(request: HttpRequest, doc_request_id: int):
    try:
        data: Dict[str, Any] = _fetch_bundle(doc_request_id)
    except APIError as e:
        messages.error(request, f"Supabase error: {escape(getattr(e, 'message', str(e)))}")
        return redirect("clerk:queue")

    header = data.get("header", {}) or {}
    lines = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline = data.get("timeline", []) or []

    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}
    for l in lines:
        l["purpose_display"] = _titleize(l.get("purpose_code"))
        l["doc_purpose"] = (
            l.get("purpose_display")
            or l.get("purpose_label")
            or l.get("purpose")
            or (l.get("details") or {}).get("purpose_code")
        )

    header["or_number"] = (
        payments.get("latest_or_number")
        or header.get("latest_or_number")
        or header.get("or_number")
        or ""
    )

    subj = subject_view(header, {})
    header["is_on_behalf"] = subj["is_on_behalf"]
    header["subject_full_name"] = subj["full_name"]
    header["subject_address"] = subj["address"]
    header["subject_age"] = subj["age"]
    header["subject_civil_status"] = subj["civil_status"]
    header["subject_nationality"] = subj["nationality"]

    return render(request, "clerk/detail.html", {
        "header": header, "status_ui": ui, "lines": lines, "payments": payments, "timeline": timeline,
    })

# =========================
# Clerk — Actions (status + printing)
# =========================
@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def mark_request_ready_for_pickup(request: HttpRequest, doc_request_id: int):
    staff_id = _staff_id(request)
    reason = (request.POST.get("reason") or "").strip() or None
    res = supabase.rpc("mark_request_ready_for_pickup", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Failed: {escape(res.error.message)}")
    else:
        messages.success(request, "Marked as ready for pickup.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def mark_for_printing(request: HttpRequest, doc_request_id: int):
    include_debug = (request.POST.get("debug") == "1")

    try:
        data: Dict[str, Any] = _fetch_bundle(doc_request_id)
    except APIError as e:
        messages.error(request, f"Supabase error: {escape(getattr(e, 'message', str(e)))}")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}

    header["or_number"] = (
        payments.get("latest_or_number")
        or payments.get("or_number")
        or _safe_str(header.get("or_number"))
    )

    outputs: List[tuple[str, bytes]] = []
    debug_items: List[Dict[str, Any]] = []
    base_dir = _pdf_templates_dir()

    for idx, line in enumerate(lines, start=1):
        doc_name = _safe_str(line.get("document_type_name") or f"doc-{idx}")
        template_file = _choose_template(doc_name, False)
        template_path = os.path.join(base_dir, template_file)

        if not os.path.exists(template_path):
            alt = os.path.join(settings.BASE_DIR, "clerk", "pdf_templates", template_file)
            if os.path.exists(alt):
                template_path = alt
            else:
                print(json.dumps({
                    "doc_index": idx, "doc_name": doc_name, "template_file": template_file,
                    "template_path": template_path, "exists": False, "reason": "Template not found"
                }, indent=2))
                continue

        base_values = _fill_fields_for_line(header, line)
        field_names = _get_all_pdf_field_names(template_path)
        merged = {name: (base_values.get(name) if str(base_values.get(name) or "").strip() else "No data")
                  for name in field_names}
        missing = [n for n in field_names if n not in base_values or str(base_values.get(n) or "").strip() == ""]

        print(json.dumps({
            "doc_index": idx,
            "doc_name": doc_name,
            "template_file": template_file,
            "template_path": template_path,
            "field_count": len(field_names),
            "missing_count": len(missing),
            "missing_fields": missing,
            "sample_values": {k: merged[k] for k in list(merged)[:10]}
        }, indent=2, default=str))

        try:
            pdf_bytes = _fill_pdf_with_values(template_path, merged)
        except Exception:
            with open(template_path, "rb") as f:
                pdf_bytes = f.read()

        safe_name = doc_name.lower().replace(" ", "-")
        out_name = f"{header.get('request_code','REQ')}-{safe_name}.pdf"
        outputs.append((out_name, pdf_bytes))
        debug_items.append({
            "output_filename": out_name,
            "doc_name": doc_name,
            "template_file": template_file,
            "template_path": template_path,
            "field_names": field_names,
            "values_written": merged,
        })

    if not outputs:
        messages.error(request, "No PDF templates found. Check your pdf_templates folder and filenames.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    if len(outputs) == 1 and not include_debug:
        fname, bytes_ = outputs[0]
        resp = HttpResponse(bytes_, content_type="application/pdf")
        if debug_items:
            d0 = debug_items[0]
            resp["X-Debug-Doc-Name"] = d0.get("doc_name","")
            resp["X-Debug-Template"] = d0.get("template_file","")
            resp["X-Debug-Fields"] = str(len(d0.get("field_names",[])))
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, b in outputs:
            zf.writestr(fname, b)
        if include_debug and debug_items:
            debug_payload = {
                "request_code": header.get("request_code"),
                "doc_request_id": doc_request_id,
                "generated_at": timezone.localtime().isoformat(),
                "items": debug_items,
            }
            zf.writestr(f"DEBUG-{header.get('request_code','REQ')}.json", json.dumps(debug_payload, indent=2))

    req_code = header.get("request_code", "REQ")
    resp = HttpResponse(zbuf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{req_code}-documents.zip"'
    return resp

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def mark_released(request: HttpRequest, doc_request_id: int):
    try:
        data = _fetch_bundle(doc_request_id)
        header = (data or {}).get("header", {}) or {}
        current_status = (header.get("status") or "")
    except Exception:
        messages.error(request, "Failed to verify request status.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    norm = re.sub(r"[\s_]+", "_", current_status.strip().upper())
    if norm != "READY_FOR_PICKUP":
        messages.error(request, "Cannot mark as RELEASED. Request must be READY_FOR_PICKUP first.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    staff_id = _staff_id(request)
    reason   = (request.POST.get("reason") or "").strip() or None
    res = supabase.rpc("mark_request_released", {
        "p_doc_request_id": doc_request_id, "p_staff_id": staff_id, "p_reason": reason
    }).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Failed: {escape(res.error.message)}")
    else:
        messages.success(request, "Marked as released.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def decline(request: HttpRequest, doc_request_id: int):
    reason = (request.POST.get("reason") or "").strip() or None
    err = _set_status(doc_request_id, "DECLINED", _staff_id(request), reason)
    messages.error(request, f"Failed: {escape(err)}") if err else messages.success(request, "Request declined.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

# =========================
# Identity verification
# =========================
STATUS_APPROVED = 3
STATUS_REJECTED = 4
STATUS_DECLINE  = 7

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def dashboard(request: HttpRequest):
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    return render(request, "clerk/dashboard.html", {
        "page_title": "Dashboard",
        "profile": profile,
        "auth": auth
    })

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def review_approve(request: HttpRequest):
    """List of ID verification requests."""
    profile = getattr(request, "person_profile", None)
    auth = request.session.get("auth")
    form = SearchVerificationRequest(request.GET or None)
    search = (form.cleaned_data.get("search") or "").strip() if (request.GET and form.is_valid()) else ""

    rows = fetch_id_verification_requests(supabase, search=search)
    if not rows and search == "":
        # Try once to surface a helpful error
        try:
            supabase.rpc("get_id_validation_requests", {}).execute()
        except APIError as e:
            messages.error(request, f"Supabase error: {escape(getattr(e, 'message', str(e)))}")

    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "clerk/resident/identity_verification_list.html",
        {
            "page_path": "Barangay Clerk / Account Verification",
            "page_title": "Account Verification",
            "page_obj": page_obj,
            "rows": page_obj.object_list,
            "form": form,
            "profile": profile,
            "auth": auth,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def person_submission_dets(request: HttpRequest, req_id: int):
    """Details of a single person's submitted verification + latest status."""
    resp = supabase.rpc("get_details", {"p_person_id": req_id}).execute()
    data = resp.data or []
    if not data:
        raise Http404("Details not found.")
    person = data[0]

    # ---- Normalize to the keys you pasted (street/sitio_purok/barangay/city etc.) ----
    raw_dt = person.get("date_requested")
    try:
        dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
        person["submitted_fmt"] = timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        person["submitted_fmt"] = raw_dt or "—"

    gps = person.get("government_programs")
    if isinstance(gps, str):
        gps = [s.strip() for s in gps.split(",") if s.strip()]
    person["government_programs"] = gps or []

    person["valid_id_files"] = person.get("valid_id_files") or []
    person["selfie_file"] = person.get("selfie_file") or None

    # Build a clean full address to avoid template logic
    parts = [
        (person.get("street") or "").strip(),
        (person.get("sitio_purok") or "").strip(),
        (person.get("barangay") or "").strip(),
        (person.get("city") or "").strip(),
    ]
    person["full_address"] = ", ".join([p for p in parts if p])

    # Latest status (optional enrichment from the list RPC)
    status_row = get_verification_status_for_person(supabase, req_id)
    if status_row:
        person["latest_status"]  = status_row.get("status_text") or person.get("latest_status") or "Pending"
        person["remarks"]        = status_row.get("latest_remarks") or person.get("remarks")

    return render(request, "clerk/resident/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "person": person,
    })


def _rpc_approve_person_by_clerk(request: HttpRequest, person_id: int, status_id: int, remarks: str | None):
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or _staff_id(request)
    if not staff_id:
        raise Http404("Staff not found in session.")
    payload = {"p_clerk_staff_id": staff_id, "p_person_id": person_id, "p_status_id": status_id, "p_remarks": remarks}
    try:
        return supabase.rpc("approve_person_by_clerk", payload).execute()
    except APIError as e:
        try:
            msg = e.message.get("message")
        except Exception:
            msg = str(e)
        raise APIError({"message": msg or "Update failed."})

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def approve_request(request: HttpRequest, req_id: int):
    try:
        _rpc_approve_person_by_clerk(request, req_id, STATUS_APPROVED, None)
        messages.success(request, "Request approved.")
    except APIError as e:
        try:
            messages.warning(request, e.message.get("message"))
        except Exception:
            messages.warning(request, "This request cannot be approved.")
    return redirect("clerk:person_details", req_id=req_id)

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def decision_request(request: HttpRequest, req_id: int):
    action = (request.POST.get("action") or "").lower()
    remarks = (request.POST.get("remarks") or "").strip()
    if action not in ("reject","decline"):
        messages.error(request, "Invalid action.")
        return redirect("clerk:person_details", req_id=req_id)
    if not remarks:
        messages.error(request, "Remarks are required.")
        return redirect("clerk:person_details", req_id=req_id)
    status_id = STATUS_REJECTED if action == "reject" else STATUS_DECLINE
    try:
        _rpc_approve_person_by_clerk(request, req_id, status_id, remarks)
        messages.success(request, f"Request marked as {'Rejected' if status_id==STATUS_REJECTED else 'Declined'}.")
    except APIError as e:
        try:
            messages.warning(request, e.message.get("message"))
        except Exception:
            messages.warning(request, "This request cannot be updated right now.")
    return redirect("clerk:person_details", req_id=req_id)

# =========================
# Business screens (stubs; clerk-only)
# =========================
def _profile_fallbacks(request: HttpRequest):
    profile = getattr(request, "person_profile", None)
    user_fullname = (
        f"{getattr(profile, 'first_name', '')} {getattr(profile, 'last_name', '')}".strip()
        if profile else (request.session.get("full_name") or "")
    )
    user_role = request.session.get("role_name") or "Clerk"
    user_role_template = "clerk"
    return user_fullname, user_role, user_role_template

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner(request: HttpRequest):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    return render(
        request,
        "business/business_owner.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner",
            "page_title": "Business Owner",
            "user_role_template": user_role_template,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner_resident(request: HttpRequest):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    form = SearchBusinessOwner()
    return render(
        request,
        "business/business_owner_resident.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "user_role_template": user_role_template,
            "form": form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_details(request: HttpRequest):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    form = BusinessDetails()
    return render(
        request,
        "business/business_details.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
            "page_title": "Business Information",
            "user_role_template": user_role_template,
            "form": form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_list(request: HttpRequest):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    form = BusinessFilters()
    return render(
        request,
        "business/business_list.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records",
            "page_title": "Business Records",
            "user_role_template": user_role_template,
            "form": form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_information(request: HttpRequest, b_id: int):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    return render(
        request,
        "business/business_information.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records / Business Details : {b_id}",
            "page_title": f"Business Details : {b_id}",
            "user_role_template": user_role_template,
        },
    )

