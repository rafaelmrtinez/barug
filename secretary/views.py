# secretary/views.py (final)
from __future__ import annotations

from typing import Any, Dict, List
from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_GET, require_http_methods

from secretary.models import Secretary
from .forms import ResidentProfileform

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase  # kept for parity / future use

# ─────────────────────────────
# Constants (mirror clerk style)
# ─────────────────────────────
SECRETARY_ROLE = "Barangay Secretary"

# Demo identity (kept as-is)
user_fullname = 'lname, fname mname suffix'
user_role = 'Barangay Secretary'
user_role_template = user_role.lower().replace(' ', '_')


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def staff_selection(request: HttpRequest) -> HttpResponse:
    return render(request, "staff/staff_selection.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_GET
def resident_suggest(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    try:
        rows = Secretary.search_resident(q) or []
        out: List[Dict[str, Any]] = []
        for r in rows[:8]:
            full_name = (r.get("person_name") or "").strip()
            code = r.get("person_code") or ""
            addr_parts = [
                (r.get("street") or "").strip(),
                (r.get("purok_sitio_name") or r.get("purok") or r.get("purok_sitio") or "").strip(),
                (r.get("barangay") or "").strip(),
                (r.get("city") or "").strip(),
            ]
            subtitle = ", ".join([p for p in addr_parts if p])
            out.append({
                "id": r.get("person_id"),
                "code": code,
                "title": full_name,
                "subtitle": subtitle,
            })
        return JsonResponse({"results": out})
    except Exception as e:
        return JsonResponse({"results": [], "error": str(e)}, status=500)


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])
def staff_selection_resident(request: HttpRequest) -> HttpResponse:
    # ── Branch: handle "Continue" (second form posts pid)
    pid = (request.POST.get('pid') or '').strip()

    # Prefer session staff_id; fallback to 6 to preserve existing behavior
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or 6

    if request.method == "POST" and pid:
        if not staff_id:
            messages.error(request, "Your session is missing staff credentials.")
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        try:
            req_id = Secretary.insert_staff_account_request(
                p_requested_by_id=staff_id,
                p_person_id=int(pid),
                p_role_id=8,  # chosen role
            )
            messages.success(request, f"Staff account request created. Ref: #{req_id}")
            # PRG pattern to avoid resubmits; reload this page
            return redirect(request.META.get("HTTP_REFERER") or request.path)
        except Exception as e:
            messages.error(request, f"Failed to create staff account request: {e}")
            return redirect(request.META.get("HTTP_REFERER") or request.path)

    # ── Original search/detail logic
    residents: List[Dict[str, Any]] = []
    res_details: Dict[str, Any] | None = None

    res_search = (request.POST.get('residentSearch') or '').strip()
    res_id = (request.POST.get('person_id') or '').strip()

    try:
        if res_search:
            residents = Secretary.search_resident(res_search) or []
        if res_id:
            rows = Secretary.get_resident_details(int(res_id)) or []
            res_details = rows[0] if rows else None
    except Exception as e:
        messages.error(request, f"Error loading resident: {e}")

    return render(request, "staff/staff_selection_resident.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'residents': residents,
        'res_details': res_details,
        'staff_id': staff_id,
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])  # accept POST if this form eventually submits here
def staff_selection_nonres(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform()
    return render(request, "person/personal_info.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form': form,
        'redirect': 'secretary:staff_selection_non-resident_docs',
    })


@session_login_required
@role_required(SECRETARY_ROLE)
@nocache
@require_http_methods(["GET", "POST"])  # template uses <form method="post">
def staff_selection_nonres_docs(request: HttpRequest) -> HttpResponse:
    form = ResidentProfileform()
    return render(request, "staff/supporting_docs.html", {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / Account Verification',
        'page_title': 'Account Verification',
        'user_role_template': user_role_template,
        'form': form,
    })
