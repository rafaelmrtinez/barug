from __future__ import annotations

from typing import Any, Dict, List
from decimal import Decimal
from datetime import datetime, date
import json
import re
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_POST
from django.core.paginator import Paginator, EmptyPage
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from zoneinfo import ZoneInfo
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.business_service_contract import IBusinessInfoService

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest

from .services.requests_service import (
    list_requests, list_business_requests, fetch_detail_bundle, build_auth_links
)
from .services.payments_service import (
    list_payment_methods, accept_payment, mark_for_printing, confirm_and_post_or
)
from .services.fees_service import (
    search_fee_items, recent_fee_changes, update_fee_amount,
    add_fee, fetch_fee_full, list_document_types, upsert_fee
)
from src.app.services.or_service import (
    IORService,
)
from .utils.ui import STATUS_UI, ACTION_LABELS, titleize

from common.send_email import send_email
from common.send_sms import send_sms
from notifications.service import notify_user
from common.logging_utils import log_business_action

# >>> NEW: import extracted helpers (behavior unchanged)
from .utils.helpers import (
    _staff_id,
    _fmt_occured_at,
    _resolve_actor_name,
    _extract_payment_method_label,
    build_page_numbers,
    split_name_main_sub,
)

from .forms import (
    ORFilters
)

TREASURER_ROLE = "Barangay Treasurer"
PH_TZ = ZoneInfo("Asia/Manila")


# ========= DASHBOARD =========
# views.py (imports)
from treasurer.services.dashboard_api import build_dashboard_payload, PH_TZ


def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

@session_login_required
@role_required(TREASURER_ROLE)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    treasurer_dashboard_service=Provide[AppContainer.treasurer_dashboard_service],
):
    user_role = _auth_role_name(request)
    auth = request.session.get('auth', {})
    person_id = auth.get('person_id')

    kpis = {
        "pending_payments": 0,
        "pending_payments_delta": None,
        "or_issued_this_week": 0,
        "or_issued_this_week_delta": None,
        "collections_this_week": 0,
        "collections_this_week_delta": None,
        "collections_this_year": 0,
        "collections_this_year_delta": None,
    }

    dashboard_json = None
    announcements = []

    try:
        payload = treasurer_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json")
    except Exception as exc:
        print("Error fetching treasurer dashboard KPIs:", exc)
    
    if person_id:
        try:
            from authentication.announcement_views import get_user_announcements
            announcements = get_user_announcements(person_id)
        except Exception as exc:
            print(f"Error fetching announcements for person {person_id}:", exc)

    return render(request, "treasurer/dashboard.html", {
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'kpis': kpis,
        'dashboard_json': dashboard_json,
        'today': datetime.now().strftime("%B %d, %Y"),
        'announcements': announcements,
    })


@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def dashboard_api(request: HttpRequest):
    rng = (request.GET.get("range") or "7d").lower()
    dtype = (request.GET.get("doc_type") or "").strip() or None
    data = build_dashboard_payload(rng, dtype)
    return JsonResponse(data, safe=True)



# ========= QUEUE =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def queue(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or ["FOR_TREASURER_REVIEW", "PAID", "FOR_PRINTING"]
    sort_order = (request.GET.get("sort") or "newest").strip()

    rows = list_requests(q, statuses, limit=500)
    EXCLUDE_DOCS = {"BARANGAY BUSINESS CLEARANCE", "CERTIFIED TRUE COPY"}
    rows = [r for r in rows if not any(dt in EXCLUDE_DOCS for dt in (r.get("doc_types") or []))]
    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {
            "label": r.get("status") or "—",
            "cls": "badge text-bg-secondary"
        }
        r["purposes_display"] = [titleize(p) for p in (r.get("purposes") or [])]
        r["created_fmt"] = _fmt_occured_at(r.get("created_at"))

    # Apply sorting
    if sort_order == "oldest":
        rows = sorted(rows, key=lambda x: x.get("created_at") or "")
    else:  # newest (default)
        rows = sorted(rows, key=lambda x: x.get("created_at") or "", reverse=True)

    # Pagination
    paginator = Paginator(rows, 10)
    try:
        page = int(request.GET.get("page", "1") or "1")
    except Exception:
        page = 1
    if page < 1:
        page = 1
    if paginator.num_pages >= 1 and page > paginator.num_pages:
        page = paginator.num_pages
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)

    status_options = [
        {"code": code, "label": meta["label"], "cls": meta["cls"], "checked": code in statuses}
        for code, meta in STATUS_UI.items()
    ]

    user_role = _auth_role_name(request)
    return render(request, "treasurer/queue.html", {
        'page_path': f'{user_role} / Resident Queue',
        'page_title': 'Resident Queue',
        "page_obj": page_obj,
        "paginator": paginator,
        "page_numbers": page_numbers,
        "is_paginated": paginator.num_pages > 1,
        "q": q or "",
        "statuses": statuses,
        "status_options": status_options,
        "sort_order": sort_order,
    })


# ========= DETAIL =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def detail(request: HttpRequest, doc_request_id: int):
    try:
        data: Dict[str, Any] = fetch_detail_bundle(doc_request_id)
    except Exception as e:
        messages.error(request, f"Supabase error: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:queue")

    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline: List[Dict[str, Any]] = data.get("timeline", []) or []

    # Preformat hero timestamp
    header["created_fmt"] = _fmt_occured_at(header.get("created_at"))

    ui = STATUS_UI.get(header.get("status")) or {
        "label": header.get("status") or "—",
        "cls": "badge text-bg-secondary"
    }

    # line presentation
    for l in lines:
        l["purpose_display"] = titleize(l.get("purpose_code"))
        details = l.get("details") or {}
        l["reason_chips"] = list(l.get("reasons_applied") or details.get("reason_tags") or [])
        l["is_exempt"] = bool(l.get("is_exempt") or False)

    # timeline presentation
    for e in timeline:
        e["action_display"] = ACTION_LABELS.get(e.get("action")) or titleize(e.get("action"))
        to_status = e.get("to_status") or (e.get("details") or {}).get("to_status")
        if to_status:
            e["to_status_display"] = (STATUS_UI.get(to_status) or {"label": titleize(to_status)}).get("label")
        raw = e.get("occurred_at") or e.get("occurredAt") or e.get("occur_time")
        dt = raw if isinstance(raw, datetime) else (parse_datetime(raw) if raw else None)
        e["occurred_at"] = dt
        e["occur_fmt"] = _fmt_occured_at(dt or raw)
        e["display_actor"] = _resolve_actor_name(e, header)

    # Payment methods list (and WAIVED id)
    methods = list_payment_methods()
    waived_method_id = next(
        (m.get("payment_method_id") for m in methods
         if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # Auth letter links
    auth_links = build_auth_links(settings, header, lines)

    # Flags for paid/OR
    def _to_f(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    amount_due = _to_f(header.get("amount_due"))
    total_paid = _to_f((payments or {}).get("total_paid"))
    latest_or = (payments or {}).get("latest_or_number") or ""
    status = (header.get("status") or "").upper()

    is_paid_no_or = ((status == "PAID") or (total_paid >= amount_due)) and (latest_or == "")
    is_paid = bool(latest_or) or (status == "PAID") or is_paid_no_or
    paid_method_label = _extract_payment_method_label(payments, timeline)

    # --- Refund tickets for this request ---
    try:
        ref_q = (supabase.table("payment_refund")
                 .select("*")
                 .eq("doc_request_id", doc_request_id)
                 .order("created_at", desc=True))
        ref_res = ref_q.execute()
        refunds_all = ref_res.data or []
    except Exception:
        refunds_all = []

    refunds_pending = [r for r in refunds_all
                       if (r.get("status") or "").upper() in ("CREATED", "PENDING", "REQUESTED")]
    latest_pending_refund = refunds_pending[0] if refunds_pending else None

    user_role = _auth_role_name(request)
    context = {
        'page_path': f'{user_role} / Request Detail',
        'page_title': 'Request Detail',
        "header": header,
        "status_ui": ui,
        "lines": lines,
        "payments": payments,
        "timeline": timeline,
        "methods": methods,
        "waived_method_id": waived_method_id,
        "auth_links": auth_links,
        "is_paid_no_or": is_paid_no_or,
        "is_paid": is_paid,
        "paid_method_label": paid_method_label,
        "doc_request_id": doc_request_id,
        "refunds_all": refunds_all,
        "refunds_pending": refunds_pending,
        "latest_pending_refund": latest_pending_refund,
        "has_pending_refund": bool(refunds_pending),
    }
    return render(request, "treasurer/detail.html", context)


# ========= TAKE PAYMENT (cash/in-person) =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def take_payment(request: HttpRequest, doc_request_id: int):
    staff_id = _staff_id(request) or 0
    method_id = int(request.POST.get("payment_method_id", "0") or 0)
    amount_paid = Decimal(request.POST.get("amount_paid", "0") or "0")

    if staff_id <= 0 or amount_paid < 0 or method_id <= 0:
        messages.error(request, "Enter a valid amount, method, and ensure your staff session is active.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    # 1) Accept payment (or waived 0.00)
    try:
        or_id = accept_payment(
            doc_request_id=doc_request_id,
            method_id=method_id,
            amount_paid=float(amount_paid),
            staff_id=staff_id,
        )
    except Exception as e:
        messages.error(request, f"Payment failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    # 2) Toast with OR details if we can
    or_res = (supabase.table("official_receipt")
              .select("or_number, amount_paid, amount_due, change_due")
              .eq("or_id", or_id).single().execute())
    if getattr(or_res, "error", None) or not or_res.data:
        messages.success(request, f"Payment posted. OR id {or_id}.")
    else:
        out = or_res.data
        messages.success(
            request,
            f"OR {out.get('or_number','—')} posted. Paid ₱{out.get('amount_paid',0):,.2f} "
            f"(due ₱{out.get('amount_due',0):,.2f}, change ₱{out.get('change_due',0):,.2f})."
        )

    # 3) Move to FOR_PRINTING
    try:
        mark_for_printing(doc_request_id=doc_request_id, staff_id=staff_id, reason="Auto-marked after payment")
        messages.info(request, "Request moved to FOR_PRINTING.")
    except Exception as e:
        messages.warning(request, f"Payment ok, but failed to mark FOR_PRINTING: {escape(str(getattr(e, 'message', e)))}")

    return redirect("treasurer:detail", doc_request_id=doc_request_id)


# ========= FEES (search/update/add/edit) =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def fees(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    try:
        per_page = int(request.GET.get("per_page", "5") or "5")
    except Exception:
        per_page = 5
    if per_page not in (5, 10, 25, 50):
        per_page = 5

    doc_types = [d.strip() for d in request.GET.getlist("doc_type") if d.strip()]
    fee_types = [k.strip() for k in request.GET.getlist("fee_type") if k.strip()]
    active_count = len(doc_types) + len(fee_types)

    items_all = search_fee_items(q)

    doc_types_all = sorted({(i.get("document_type") or "").strip()
                            for i in items_all if (i.get("document_type") or "").strip()})
    fee_types_all = sorted({(i.get("fee_type") or "").strip()
                            for i in items_all if (i.get("fee_type") or "").strip()})

    def passes_filters(row: Dict[str, Any]) -> bool:
        dt = (row.get("document_type") or "").strip()
        ft = (row.get("fee_type") or "").strip()
        if doc_types and dt not in doc_types:
            return False
        if fee_types and ft not in fee_types:
            return False
        return True

    filtered = [r for r in items_all if passes_filters(r)]

    for r in filtered:
        main, sub = split_name_main_sub(r.get("name") or "")
        r["name_main"] = main
        r["name_sub"] = sub

    paginator = Paginator(filtered, per_page)
    try:
        page = int(request.GET.get("page", "1") or "1")
    except Exception:
        page = 1
    if page < 1:
        page = 1
    if paginator.num_pages >= 1 and page > paginator.num_pages:
        page = paginator.num_pages
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)
    history = recent_fee_changes(limit=11)

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Fees',
        'page_title': 'Fees',
        "q": q or "",
        "per_page": per_page,
        "doc_types": doc_types,
        "fee_types": fee_types,
        "doc_types_all": doc_types_all,
        "fee_types_all": fee_types_all,
        "active_count": active_count,
        "is_paginated": paginator.num_pages > 1,
        "paginator": paginator,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "history": history,
    }
    return render(request, "treasurer/fees.html", ctx)


@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def fee_update(request: HttpRequest):
    staff_id = _staff_id(request) or 0
    fee_code = (request.POST.get("fee_code") or "").strip()
    reason = (request.POST.get("reason") or "").strip() or None
    try:
        new_amount = float(Decimal(request.POST.get("new_amount", "0")))
    except Exception:
        messages.error(request, "Invalid amount.")
        return redirect("treasurer:fees")

    if staff_id <= 0 or not fee_code or new_amount < 0:
        messages.error(request, "Provide a valid fee code and amount; ensure staff session is active.")
        return redirect("treasurer:fees")

    try:
        update_fee_amount(fee_code=fee_code, new_amount=new_amount, staff_id=staff_id, reason=reason)
        messages.success(request, f"{fee_code} updated to ₱{new_amount:,.2f}.")
    except Exception as e:
        messages.error(request, f"Update failed: {escape(str(getattr(e, 'message', e)))}")
    return redirect("treasurer:fees")


@session_login_required
@role_required(TREASURER_ROLE)
def fee_add(request: HttpRequest):
    doc_types = list_document_types()
    units = ["per_doc", "per_copy", "per_event", "per_month", "per_year",
             "per_hour", "per_unit_per_day", "per_use"]

    if request.method != "POST":
        return render(request, "treasurer/fee_add.html", {"doc_types": doc_types, "units": units})

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_add")

    use_new = (request.POST.get("use_new_doc") == "1")
    doc_type_name = (request.POST.get("doc_type_name_new") or "").strip() if use_new \
        else (request.POST.get("doc_type_name") or "").strip()

    fee_code = (request.POST.get("fee_code") or "").strip()
    fee_name = (request.POST.get("fee_name") or "").strip()
    unit = (request.POST.get("unit") or "per_doc").strip()

    try:
        current_amount = float(Decimal(request.POST.get("current_amount") or "0"))
    except Exception:
        current_amount = -1
    try:
        max_amount_raw = (request.POST.get("max_amount") or "").strip()
        max_amount = float(Decimal(max_amount_raw)) if max_amount_raw != "" else None
    except Exception:
        max_amount = None

    ex_ftj = bool(request.POST.get("ex_ftj"))
    ex_senior = bool(request.POST.get("ex_senior"))
    ex_pwd = bool(request.POST.get("ex_pwd"))
    ex_indigent = bool(request.POST.get("ex_indigent"))
    ex_student = bool(request.POST.get("ex_student"))
    is_active = bool(request.POST.get("is_active")) if request.POST.get("is_active") is not None else True

    purpose_code = (request.POST.get("purpose_code") or "").strip() or None
    purpose_label = (request.POST.get("purpose_label") or "").strip() or None
    default_offense_no = (request.POST.get("default_offense_no") or "").strip()
    default_offense_no = int(default_offense_no) if default_offense_no.isdigit() else None

    try:
        default_details = json.loads(request.POST.get("default_details") or "{}")
        if not isinstance(default_details, dict):
            default_details = {}
    except Exception:
        default_details = {}

    surcharges = []
    for n, key in enumerate(("s1", "s2", "s3"), start=1):
        val = (request.POST.get(key) or "").strip()
        if val:
            try:
                surcharges.append({"offense_no": n, "percent": float(Decimal(val))})
            except Exception:
                pass
    p_surcharges = surcharges or None

    reason = (request.POST.get("reason") or "Initial create").strip() or "Initial create"

    if not doc_type_name or not fee_code or not fee_name or current_amount is None or current_amount < 0:
        messages.error(request, "Please fill in Document Type, Fee Code/Name, and a valid Current Amount.")
        return redirect("treasurer:fee_add")

    payload = {
        "p_doc_type_name": doc_type_name,
        "p_fee_code": fee_code,
        "p_fee_name": fee_name,
        "p_current_amount": current_amount,
        "p_unit": unit,
        "p_max_amount": max_amount,
        "p_exempt_ftj": ex_ftj,
        "p_exempt_senior": ex_senior,
        "p_exempt_pwd": ex_pwd,
        "p_exempt_indigent": ex_indigent,
        "p_exempt_student": ex_student,
        "p_is_active": is_active,
        "p_purpose_code": purpose_code,
        "p_purpose_label": purpose_label,
        "p_default_details": default_details,
        "p_default_offense_no": default_offense_no,
        "p_surcharges": p_surcharges,
        "p_changed_by_staff_id": _staff_id(request) or 0,
        "p_reason": reason,
    }

    try:
        add_fee(payload)
    except Exception as e:
        messages.error(request, f"Add fee failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_add")

    messages.success(request, f"Saved: {fee_code} – {fee_name} (Type: {doc_type_name}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")




# ========= FEES (split add screens) =========
from django.views.decorators.http import require_GET, require_POST


@session_login_required
@role_required(TREASURER_ROLE)
def fee_add_existing(request: HttpRequest):
    """
    Add a fee using an EXISTING document type.
    If ?doc_type=... is present, lock the dropdown and show a readonly field.
    Renders: fee_purpose.html
    """
    doc_types = list_document_types()

    # NEW: read suggested doc type from querystring (when coming from fees.html)
    preselected = (request.GET.get("doc_type") or "").strip() or None

    if request.method != "POST":
        user_role = _auth_role_name(request)
        return render(
            request,
            "treasurer/fee_purpose.html",
            {
                'page_path': f'{user_role} / Add Fee (Existing Type)',
                'page_title': 'Add Fee (Existing Type)',
                "doc_types": doc_types,
                "preselected_doc_type": preselected,  # <-- tells template to disable dropdown
            },
        )

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_add_existing")

    # Existing doc type (required here; comes from dropdown OR hidden input when preselected)
    doc_type_name = (request.POST.get("doc_type_name") or "").strip()

    fee_code = (request.POST.get("fee_code") or "").strip()
    fee_name = (request.POST.get("fee_name") or "").strip()
    unit = "per_doc"  # fixed

    try:
        current_amount = float(Decimal(request.POST.get("current_amount") or "0"))
    except Exception:
        current_amount = -1

    purpose_code  = (request.POST.get("purpose_code") or "").strip() or None
    purpose_label = (request.POST.get("purpose_label") or "").strip() or None
    default_offense_no_raw = (request.POST.get("default_offense_no") or "").strip()
    default_offense_no = int(default_offense_no_raw) if default_offense_no_raw.isdigit() else None

    try:
        default_details = json.loads(request.POST.get("default_details") or "{}")
        if not isinstance(default_details, dict):
            default_details = {}
    except Exception:
        default_details = {}

    ex_senior  = bool(request.POST.get("ex_senior"))
    ex_pwd     = bool(request.POST.get("ex_pwd"))
    ex_student = bool(request.POST.get("ex_student"))
    is_active  = bool(request.POST.get("is_active")) if request.POST.get("is_active") is not None else True
    reason     = (request.POST.get("reason") or "Initial create").strip() or "Initial create"

    if not doc_type_name or not fee_code or not fee_name or current_amount is None or current_amount < 0:
        messages.error(request, "Please fill Document Type, Fee Code/Name, and a valid Current Amount.")
        return redirect("treasurer:fee_add_existing" + (f"?doc_type={doc_type_name}" if doc_type_name else ""))

    payload = {
        "p_doc_type_name": doc_type_name,
        "p_fee_code": fee_code,
        "p_fee_name": fee_name,
        "p_current_amount": current_amount,
        "p_unit": unit,
        "p_max_amount": None,
        "p_exempt_ftj": False,
        "p_exempt_senior": ex_senior,
        "p_exempt_pwd": ex_pwd,
        "p_exempt_indigent": False,
        "p_exempt_student": ex_student,
        "p_is_active": is_active,
        "p_purpose_code": purpose_code,
        "p_purpose_label": purpose_label,
        "p_default_details": default_details,
        "p_default_offense_no": default_offense_no,
        "p_surcharges": None,
        "p_changed_by_staff_id": staff_id,
        "p_reason": reason,
    }

    try:
        add_fee(payload)
    except Exception as e:
        messages.error(request, f"Add fee failed: {escape(str(getattr(e, 'message', e)))}")
        # keep the context when we bounce back
        return redirect("treasurer:fee_add_existing" + (f"?doc_type={doc_type_name}" if doc_type_name else ""))

    messages.success(request, f"Saved: {fee_code} – {fee_name} (Type: {doc_type_name}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")


@session_login_required
@role_required(TREASURER_ROLE)
def fee_add_new(request: HttpRequest):
    """
    Add a fee WITH a NEW document type (exactly like old combined view when switch ON).
    Renders: fee_add.html
    """
    doc_types = list_document_types()  # just for reference/help if needed

    if request.method != "POST":
        return render(request, "treasurer/fee_add.html", {"doc_types": doc_types})

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_add_new")

    # New doc type (required here)
    doc_type_name_new = (request.POST.get("doc_type_name_new") or "").strip()

    fee_code = (request.POST.get("fee_code") or "").strip()
    fee_name = (request.POST.get("fee_name") or "").strip()
    unit = "per_doc"  # fixed

    try:
        current_amount = float(Decimal(request.POST.get("current_amount") or "0"))
    except Exception:
        current_amount = -1

    # PURPOSE (single)
    purpose_code  = (request.POST.get("purpose_code") or "").strip() or None
    purpose_label = (request.POST.get("purpose_label") or "").strip() or None
    default_offense_no_raw = (request.POST.get("default_offense_no") or "").strip()
    default_offense_no = int(default_offense_no_raw) if default_offense_no_raw.isdigit() else None

    try:
        default_details = json.loads(request.POST.get("default_details") or "{}")
        if not isinstance(default_details, dict):
            default_details = {}
    except Exception:
        default_details = {}

    ex_senior  = bool(request.POST.get("ex_senior"))
    ex_pwd     = bool(request.POST.get("ex_pwd"))
    ex_student = bool(request.POST.get("ex_student"))
    is_active  = bool(request.POST.get("is_active")) if request.POST.get("is_active") is not None else True
    reason     = (request.POST.get("reason") or "Initial create").strip() or "Initial create"

    if not doc_type_name_new or not fee_code or not fee_name or current_amount is None or current_amount < 0:
        messages.error(request, "Please fill New Document Type, Fee Code/Name, and a valid Current Amount.")
        return redirect("treasurer:fee_add_new")

    payload = {
        "p_doc_type_name": doc_type_name_new,
        "p_fee_code": fee_code,
        "p_fee_name": fee_name,
        "p_current_amount": current_amount,
        "p_unit": unit,
        "p_max_amount": None,
        "p_exempt_ftj": False,
        "p_exempt_senior": ex_senior,
        "p_exempt_pwd": ex_pwd,
        "p_exempt_indigent": False,
        "p_exempt_student": ex_student,
        "p_is_active": is_active,
        # purpose fields
        "p_purpose_code": purpose_code,
        "p_purpose_label": purpose_label,
        "p_default_details": default_details,
        "p_default_offense_no": default_offense_no,
        "p_surcharges": None,
        "p_changed_by_staff_id": staff_id,
        "p_reason": reason,
    }

    try:
        add_fee(payload)
    except Exception as e:
        messages.error(request, f"Add fee failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_add_new")

    messages.success(request, f"Saved: {fee_code} – {fee_name} (NEW Type: {doc_type_name_new}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")


@session_login_required
@role_required(TREASURER_ROLE)
def fee_add_new(request: HttpRequest):
    """
    Add a fee WITH a NEW document type (no switch; always new).
    Renders: fee_add.html
    """
    # We still pull doc_types in case you want hints or client-side checks later.
    doc_types = list_document_types()

    if request.method != "POST":
        user_role = _auth_role_name(request)
        return render(request, "treasurer/fee_add.html", {
            'page_path': f'{user_role} / Add Fee (New Type)',
            'page_title': 'Add Fee (New Type)',
            "doc_types": doc_types,
        })

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_add_new")

    # Always NEW doc type on this screen
    doc_type_name_new = (request.POST.get("doc_type_name_new") or "").strip()

    fee_code = (request.POST.get("fee_code") or "").strip()
    fee_name = (request.POST.get("fee_name") or "").strip()

    # unit fixed to per_doc (hidden in template)
    unit = "per_doc"

    # amounts / flags
    try:
        current_amount = float(Decimal(request.POST.get("current_amount") or "0"))
    except Exception:
        current_amount = -1

    ex_senior  = bool(request.POST.get("ex_senior"))
    ex_pwd     = bool(request.POST.get("ex_pwd"))
    ex_student = bool(request.POST.get("ex_student"))
    is_active  = True if request.POST.get("is_active") is not None else False

    reason = (request.POST.get("reason") or "Initial create").strip() or "Initial create"

    if not doc_type_name_new or not fee_code or not fee_name or current_amount is None or current_amount < 0:
        messages.error(request, "Please fill New Document Type, Fee Code/Name, and a valid Current Amount.")
        return redirect("treasurer:fee_add_new")

    payload = {
        "p_doc_type_name": doc_type_name_new,
        "p_fee_code": fee_code,
        "p_fee_name": fee_name,
        "p_current_amount": current_amount,
        "p_unit": unit,
        "p_max_amount": None,
        "p_exempt_ftj": False,           # not exposed in the split pages
        "p_exempt_senior": ex_senior,
        "p_exempt_pwd": ex_pwd,
        "p_exempt_indigent": False,      # not exposed in the split pages
        "p_exempt_student": ex_student,
        "p_is_active": is_active,
        "p_purpose_code": None,
        "p_purpose_label": None,
        "p_default_details": {},
        "p_default_offense_no": None,
        "p_surcharges": None,            # not exposed in the split pages
        "p_changed_by_staff_id": staff_id,
        "p_reason": reason,
    }

    try:
        add_fee(payload)
    except Exception as e:
        messages.error(request, f"Add fee failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_add_new")

    messages.success(request, f"Saved: {fee_code} – {fee_name} (NEW Type: {doc_type_name_new}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")


# at the imports top (already have _fmt_occured_at)
from .services.fees_service import get_fee_timeline

@session_login_required
@role_required(TREASURER_ROLE)
def fee_edit(request: HttpRequest, fee_code: str):
    # Load fee + related info
    try:
        data = fetch_fee_full(fee_code)
    except Exception as e:
        messages.error(request, f"Load failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fees")

    fee = (data.get("fee") or {})
    purposes = data.get("purposes") or []
    surcharges = data.get("surcharges") or []
    doc_types = list_document_types()
    units = ["per_doc", "per_copy", "per_event", "per_month", "per_year",
             "per_hour", "per_unit_per_day", "per_use"]

    # ===== GET: render form + timeline =====
    if request.method != "POST":
        # Build timeline (pre-format for template)
        timeline = []
        try:
            tl = get_fee_timeline(fee_code) or []
            for e in tl:
                occ = e.get("occurred_at")
                raw_event = (e.get("event") or "LOG").upper()
                # normalize + preformat
                d = e.get("details") or {}
                if isinstance(d, str):
                    try:
                        d = json.loads(d) or {}
                    except Exception:
                        d = {}

                item = {
                    **e,
                    "event": raw_event,
                    "event_display": raw_event.replace("_", " "),
                    "occur_fmt": _fmt_occured_at(occ),
                    "details": d,
                    "summary": None,
                }

                # nice summary for amount changes
                if raw_event == "FEE_UPDATED" and ("old_amount" in d or "new_amount" in d):
                    oldv = d.get("old_amount")
                    newv = d.get("new_amount")
                    try:
                        item["summary"] = f"Amount changed: ₱{(oldv or 0):,.2f} → ₱{(newv or 0):,.2f}"
                    except Exception:
                        item["summary"] = "Amount changed."

                timeline.append(item)
        except Exception:
            timeline = []

        user_role = _auth_role_name(request)
        return render(request, "treasurer/fee_edit.html", {
            'page_path': f'{user_role} / Edit Fee',
            'page_title': 'Edit Fee',
            "fee_code": fee_code,
            "fee": fee,
            "purposes": purposes,
            "surcharges": surcharges,
            "doc_types": doc_types,
            "units": units,
            "fee_timeline": timeline,   # <- for Change History panel
        })

    # ===== POST: save changes =====
    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_edit", fee_code=fee_code)

    # helpers
    def _as_bool(name: str) -> bool | None:
        """
        Interprets '1', 'true', 'on', 'yes' as True, '0' etc. as False.
        With hidden '0' inputs plus checkbox '1', this returns True/False (not None).
        """
        v = request.POST.get(name)
        if v is None:
            return None
        v = str(v).strip().lower()
        return v in ("1", "true", "on", "yes")

    def _as_float(name: str) -> float | None:
        raw = (request.POST.get(name) or "").strip()
        if raw == "":
            return None
        try:
            return float(Decimal(raw))
        except Exception:
            return None

    payload: Dict[str, Any] = {
        "p_fee_code": fee_code,
        "p_changed_by_staff_id": staff_id,
        "p_new_name": (request.POST.get("fee_name") or "").strip() or None,
        "p_new_unit": (request.POST.get("unit") or "").strip() or None,
        "p_new_current_amount": _as_float("current_amount"),
        "p_new_max_amount": _as_float("max_amount"),
        # fixed: booleans from switches (unchecked -> "0" -> False)
        "p_exempt_ftj": _as_bool("ex_ftj"),
        "p_exempt_senior": _as_bool("ex_senior"),
        "p_exempt_pwd": _as_bool("ex_pwd"),
        "p_exempt_indigent": _as_bool("ex_indigent"),
        "p_exempt_student": _as_bool("ex_student"),
        "p_is_active": _as_bool("is_active"),
        "p_doc_type_name": (request.POST.get("doc_type_name") or "").strip() or None,
        "p_reason": (request.POST.get("reason") or "").strip() or None,
    }

    # purposes (dynamic rows)
    purp_rows: List[Dict[str, Any]] = []
    idx = 0
    while True:
        idx += 1
        pc = (request.POST.get(f"purp_{idx}_code") or "").strip()
        lbl = (request.POST.get(f"purp_{idx}_label") or "").strip()
        dt_override = (request.POST.get(f"purp_{idx}_dtype") or "").strip()
        det = (request.POST.get(f"purp_{idx}_details") or "").strip()
        off = (request.POST.get(f"purp_{idx}_offense") or "").strip()

        if not pc and not lbl and not det and not off and not dt_override:
            if idx > 50:
                break
            continue

        try:
            details = json.loads(det) if det else {}
            if not isinstance(details, dict):
                details = {}
        except Exception:
            details = {}

        purp_rows.append({
            "request_document_type_name": dt_override or None,
            "purpose_code": pc or None,
            "purpose_label": lbl or None,
            "default_details": details,
            "default_offense_no": int(off) if off.isdigit() else None,
        })

    if purp_rows:
        payload["p_purposes"] = purp_rows

    # surcharges 1..3
    sr: List[Dict[str, Any]] = []
    for k in ("1", "2", "3"):
        val = (request.POST.get(f"surcharge_{k}") or "").strip()
        if val != "":
            try:
                sr.append({"offense_no": int(k), "percent": float(Decimal(val))})
            except Exception:
                pass
    if sr:
        payload["p_surcharges"] = sr

    # save
    try:
        upsert_fee(payload)
    except Exception as e:
        messages.error(request, f"Update failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_edit", fee_code=fee_code)

    messages.success(request, f"{fee_code} saved.")
    return redirect("treasurer:fee_edit", fee_code=fee_code)



# ---------- BUSINESS QUEUE ----------
@session_login_required
@role_required(TREASURER_ROLE)
def business_queue(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or [
        "FOR_TREASURER_REVIEW", "PAID", "FOR_PRINTING", "READY_FOR_PICKUP", "RELEASED", "DECLINED"
    ]
    TARGET_DOCS = {"BARANGAY BUSINESS CLEARANCE", "CERTIFIED TRUE COPY"}
    raw_rows = list_business_requests(q, statuses, limit=100)

    rows: List[Dict[str, Any]] = []
    for r in raw_rows:
        docs = [(d or "").strip() for d in (r.get("doc_types") or [])]
        if any(d in TARGET_DOCS for d in docs):
            r["status_ui"] = STATUS_UI.get(r.get("status")) or {
                "label": r.get("status") or "—",
                "cls": "badge text-bg-secondary",
            }
            r["purposes_display"] = [titleize(p) for p in (r.get("purposes") or [])]
            r["doc_types"] = [d for d in docs if d in TARGET_DOCS]
            r["created_fmt"] = _fmt_occured_at(r.get("created_at"))
            rows.append(r)

    user_role = _auth_role_name(request)
    return render(request, "treasurer/business_queue.html", {
        'page_path': f'{user_role} / Business Queue',
        'page_title': 'Business Queue',
        "rows": rows,
        "q": q or "",
        "statuses": statuses,
    })


# ---------- BUSINESS DETAIL ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_detail(request: HttpRequest, business_id: int, doc_request_id: int):
    biz_res = supabase.rpc("get_business_details", {"p_business_id": business_id}).execute()
    biz = (biz_res.data[0] if (biz_res and getattr(biz_res, "data", None)) else {}) or {}
    biz["has_business_clearance"] = bool(
        biz.get("has_business_clearance") or biz.get("has_brgy_clearance")
    )

    header: Dict[str, Any] = {}
    payments: Dict[str, Any] = {}
    lines: List[Dict[str, Any]] = []
    try:
        bundle = fetch_detail_bundle(doc_request_id)
        header = bundle.get("header") or {}
        payments = bundle.get("payments") or {}
        lines = bundle.get("lines") or []
    except Exception as e:
        messages.warning(request, f"Could not load request details: {escape(str(getattr(e,'message',e)))}")

    document_type_name = None
    if lines:
        document_type_name = (lines[0].get("document_type_name") or "").strip()

    ctc_mode = (document_type_name or "").upper() == "CERTIFIED TRUE COPY"
    ctc_ref_header: Dict[str, Any] = {}
    ctc_ref_lines: List[Dict[str, Any]] = []
    ctc_ref_request_id: int | None = None

    if ctc_mode:
        try:
            det = (lines[0].get("details") or {}) if lines else {}
            ctc_ref_request_id = int(det.get("reference_request_id") or 0) or None
            if not ctc_ref_request_id:
                for l in lines:
                    d = l.get("details") or {}
                    if d.get("reference_request_id"):
                        ctc_ref_request_id = int(d["reference_request_id"])
                        break
            if ctc_ref_request_id:
                ref_bundle = fetch_detail_bundle(ctc_ref_request_id)
                ctc_ref_header = ref_bundle.get("header") or {}
                ctc_ref_lines = ref_bundle.get("lines") or []
            else:
                messages.warning(request, "CTC: no reference_request_id found on line details.")
        except Exception as e:
            messages.warning(request, f"CTC: failed to load reference clearance details: {escape(str(getattr(e,'message',e)))}")

    methods = list_payment_methods()
    waived_method_id = next(
        (m.get("payment_method_id") for m in methods if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # === NEW: Detect business renewal and override amount_due ===
    is_business_renewal = False
    renewal_totals = {}
    
    try:
        for l in lines:
            det = l.get("details") or {}
            # Check if this is a business clearance with renewal data
            if det.get("renewal_breakdown") and det.get("years_count"):
                is_business_renewal = True
                renewal_totals = {
                    "total_base_fee": det.get("total_base_fee", 0),
                    "total_surcharge": det.get("total_surcharge", 0),
                    "total_amount": det.get("total_amount", 0),
                    "years_count": det.get("years_count", 0),
                    "period_type": det.get("period_type", ""),
                    "period_year": det.get("period_year", ""),
                }
                
                # Override the header amount_due with the actual total from renewal breakdown
                header["amount_due"] = det.get("total_amount", 0)
                print(f"[treasurer business_detail] Business renewal detected: {renewal_totals['years_count']} year(s), total: ₱{renewal_totals['total_amount']:.2f}")
                break
    except Exception as e:
        print(f"[treasurer business_detail] Error extracting renewal breakdown: {e}")
        pass

    user_role = _auth_role_name(request)
    return render(request, "treasurer/business_details.html", {
        'page_path': f'{user_role} / Business Details',
        'page_title': 'Business Details',
        "biz": biz,
        "doc_request_id": doc_request_id,
        "header": header,
        "payments": payments,
        "methods": methods,
        "waived_method_id": waived_method_id,
        # "clearances": clearances,
        # "year_status": year_status,
        # "last_cleared_year": last_cleared_year,
        "document_type_name": document_type_name,
        "status_ui": STATUS_UI.get(header.get("status") or "") or {
            "label": header.get("status") or "—",
            "cls": "badge text-bg-secondary"
        },
        "ctc_mode": ctc_mode,
        "ctc_ref_request_id": ctc_ref_request_id,
        "ctc_ref_header": ctc_ref_header,
        "ctc_ref_lines": ctc_ref_lines,
        "is_business_renewal": is_business_renewal,
        "renewal_totals": renewal_totals,
    })


# ---------- PAY & PRINT (business shortcut) ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def business_pay_and_print(request: HttpRequest, business_id: int, doc_request_id: int):
    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session required.")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    print(f"[PAY DEBUG] POST data: {dict(request.POST)}")
    print(f"[PAY DEBUG] staff_id: {staff_id}")
    
    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
        amount_paid = float(Decimal(request.POST.get("amount_paid", "0") or "0"))
        print(f"[PAY DEBUG] method_id: {method_id}, amount_paid: {amount_paid}")
    except Exception as e:
        print(f"[PAY DEBUG] Parse error: {e}")
        messages.error(request, "Invalid payment fields.")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    or_id = None
    try:
        print(f"[PAY DEBUG] Calling accept_payment with doc_request_id={doc_request_id}, method_id={method_id}, amount_paid={amount_paid}, staff_id={staff_id}")
        or_id = accept_payment(
            doc_request_id=doc_request_id,
            method_id=method_id,
            amount_paid=amount_paid,
            staff_id=staff_id,
        )
        print(f"[PAY DEBUG] accept_payment returned or_id: {or_id}")
    except Exception as e:
        print(f"[PAY DEBUG] accept_payment FAILED: {e}")
        import traceback
        print(f"[PAY DEBUG] Traceback: {traceback.format_exc()}")
        messages.error(request, f"Payment failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    try:
        or_res = (supabase.table("official_receipt")
                  .select("or_number, amount_paid, amount_due, change_due")
                  .eq("or_id", or_id).single().execute())
        if getattr(or_res, "data", None):
            o = or_res.data
            messages.success(
                request,
                f"OR {o.get('or_number','—')} posted. Paid ₱{o.get('amount_paid',0):,.2f} "
                f"(due ₱{o.get('amount_due',0):,.2f}, change ₱{o.get('change_due',0):,.2f})."
            )
        else:
            messages.success(request, f"Payment posted. OR id {or_id}.")
    except Exception:
        messages.success(request, f"Payment posted. OR id {or_id}.")

    try:
        print(f"[PAY DEBUG] Setting business flag for business_id={business_id}")
        res = supabase.rpc("set_business_has_clearance_true", {"p_business_id": business_id}).execute()
        print(f"[PAY DEBUG] Business flag result: {res.data}, error: {getattr(res, 'error', None)}")
        messages.info(request, "Business flag set: has_business_clearance = TRUE.")
    except Exception as e:
        print(f"[PAY DEBUG] Business flag FAILED: {e}")
        messages.warning(request, f"Payment ok, but failed to set business flag: {escape(str(getattr(e,'message',e)))}")

    # Update business status to ACTIVE after successful renewal payment
    try:
        print(f"[PAY DEBUG] Updating business status to ACTIVE for business_id={business_id}")
        update_res = (
            supabase.table("business")
            .update({"business_status_id": 1})  # 1 = ACTIVE
            .eq("business_id", business_id)
            .execute()
        )
        print(f"[PAY DEBUG] Business status update result: {update_res.data}, error: {getattr(update_res, 'error', None)}")
        messages.success(request, "Business status updated to ACTIVE.")
    except Exception as e:
        print(f"[PAY DEBUG] Business status update FAILED: {e}")
        messages.warning(request, f"Payment ok, but failed to update business status: {escape(str(getattr(e,'message',e)))}")

    # Mark all renewal requests as PAID
    try:
        print(f"[PAY DEBUG] Fetching renewal request IDs from document details")
        # Fetch the document bundle to get line details
        try:
            bundle = fetch_detail_bundle(doc_request_id)
            lines = bundle.get("lines") or []
        except Exception as e:
            print(f"[PAY DEBUG] Failed to fetch bundle: {e}")
            lines = []
        
        renewal_request_ids = []
        if lines:
            for line in lines:
                details = line.get("details") or {}
                ids = details.get("renewal_request_ids", [])
                if ids:
                    renewal_request_ids.extend(ids)
        
        print(f"[PAY DEBUG] Found renewal request IDs: {renewal_request_ids}")
        
        if renewal_request_ids:
            # Get OR number and payment date for the renewal requests
            or_number = None
            paid_on = None
            try:
                or_res = supabase.table("official_receipt").select("or_number, created_at").eq("or_id", or_id).single().execute()
                if or_res.data:
                    or_number = or_res.data.get("or_number")
                    paid_on = or_res.data.get("created_at")
            except Exception as e:
                print(f"[PAY DEBUG] Could not fetch OR details: {e}")
            
            # Fetch renewal request details to get period_year for each
            renewal_years = {}
            try:
                for renewal_id in renewal_request_ids:
                    rr_res = supabase.table("renewal_request").select("period_year").eq("renewal_request_id", renewal_id).single().execute()
                    if rr_res.data:
                        renewal_years[renewal_id] = rr_res.data.get("period_year")
            except Exception as e:
                print(f"[PAY DEBUG] Could not fetch renewal request years: {e}")
            
            # Update all renewal requests to PAID
            for renewal_id in renewal_request_ids:
                try:
                    update_data = {
                        "paid": True,
                        "or_id": or_id,
                    }
                    if or_number:
                        update_data["or_number"] = or_number
                    if paid_on:
                        update_data["paid_on"] = paid_on
                    
                    renewal_update = (
                        supabase.table("renewal_request")
                        .update(update_data)
                        .eq("renewal_request_id", renewal_id)
                        .execute()
                    )
                    print(f"[PAY DEBUG] Marked renewal_request_id {renewal_id} as PAID with OR {or_number}")
                    
                    # Also update business_clearance_status_record for paid history
                    period_year = renewal_years.get(renewal_id)
                    if period_year:
                        try:
                            status_update = (
                                supabase.table("business_clearance_status_record")
                                .update({
                                    "or_number": or_number,
                                    "paid_on": paid_on
                                })
                                .eq("business_id", business_id)
                                .eq("period_year", period_year)
                                .eq("period_type", "ANNUAL")
                                .execute()
                            )
                            print(f"[PAY DEBUG] Updated business_clearance_status_record for year {period_year}")
                        except Exception as e:
                            print(f"[PAY DEBUG] Failed to update business_clearance_status_record for year {period_year}: {e}")
                except Exception as e:
                    print(f"[PAY DEBUG] Failed to mark renewal_request_id {renewal_id} as paid: {e}")
            
            messages.success(request, f"Marked {len(renewal_request_ids)} renewal request(s) as PAID.")
    except Exception as e:
        print(f"[PAY DEBUG] Failed to mark renewal requests as paid: {e}")
        import traceback
        print(f"[PAY DEBUG] Traceback: {traceback.format_exc()}")
        messages.warning(request, f"Payment ok, but failed to mark renewal requests as paid: {escape(str(getattr(e,'message',e)))}")

    try:
        print(f"[PAY DEBUG] Marking for printing doc_request_id={doc_request_id}")
        mark_for_printing(
            doc_request_id=doc_request_id,
            staff_id=staff_id,
            reason="Auto: after payment from Business Details"
        )
        print(f"[PAY DEBUG] Mark for printing SUCCESS")
        messages.info(request, "Request moved to FOR_PRINTING.")
    except Exception as e:
        print(f"[PAY DEBUG] Mark for printing FAILED: {e}")
        messages.warning(request, f"Payment ok, but failed to move to FOR_PRINTING: {escape(str(getattr(e,'message',e)))}")

    return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)


# ---------- BUSINESS RENEWAL LIST ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_renewal(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    period_types = [p.strip().upper() for p in request.GET.getlist("period_type") if p.strip()]
    year = (request.GET.get("year") or "").strip()
    paid_filters = [p.strip().lower() for p in request.GET.getlist("paid") if p.strip()]
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 10
    if per_page not in (5, 10, 25, 50):
        per_page = 10

    query = supabase.table("renewal_request").select("*").order("created_at", desc=True)

    if q:
        or_parts = [f"request_code.ilike.%{q}%", f"or_number.ilike.%{q}%"]
        if q.isdigit():
            or_parts += [f"period_year.eq.{q}", f"business_id.eq.{q}"]
        query = query.or_(",".join(or_parts))

    if year.isdigit():
        query = query.eq("period_year", int(year))
    if period_types:
        query = query.in_("period_type", period_types)

    res = query.limit(500).execute()
    rows = res.data or []

    STATUS_ID_MAP = {8: "FOR_TREASURER_REVIEW", 9: "PAID"}

    if paid_filters:
        want_paid = "paid" in paid_filters and "unpaid" not in paid_filters
        want_unpaid = "unpaid" in paid_filters and "paid" not in paid_filters
        if want_paid:
            rows = [r for r in rows if r.get("request_status_id") == 9]
        elif want_unpaid:
            rows = [r for r in rows if r.get("request_status_id") == 8]

    def _to_float(v):
        try:
            return float(v)
        except Exception:
            return None

    def _sec(ts):
        if not ts:
            return ""
        s = str(ts)
        return s[:19]  # YYYY-MM-DDTHH:MM:SS

    def _fmt_iso_local(ts):
        if not ts:
            return None
        dt = parse_datetime(str(ts))
        if not dt:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")

    def _epoch(ts) -> float:
        dt = parse_datetime(str(ts)) if ts else None
        if not dt:
            return 0.0
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        return dt.timestamp()

    # decorate each row
    for r in rows:
        status_name = STATUS_ID_MAP.get(r.get("request_status_id"), "—")
        ui = STATUS_UI.get(status_name) or {"label": status_name, "cls": "badge text-bg-secondary"}
        r["status_name"] = status_name
        r["status_ui"] = ui

        ptype = (r.get("period_type") or "").upper()
        yr = r.get("period_year")
        qtr = r.get("period_quarter")
        if ptype == "QUARTERLY":
            r["period_label"] = f"Q{qtr} {yr}" if (yr and qtr) else (ptype or "—")
        else:
            r["period_label"] = str(yr or "—")

        r["base_fee_quote_f"] = _to_float(r.get("base_fee_quote"))
        r["surcharge_quote_f"] = _to_float(r.get("surcharge_quote"))
        r["total_quote_f"] = _to_float(r.get("total_quote"))
        r["paid_on_disp"] = _fmt_iso_local(r.get("paid_on"))

    # ------- visual headers without reordering (keep latest-first from DB) -------
    def _gkey(r):
        return (
            r.get("business_id"),
            (r.get("period_type") or "").upper(),
            r.get("created_by_user_id"),
            _sec(r.get("created_at")),
        )

    grouped_rows = []
    last_key = None
    for r in rows:  # DO NOT sort here; preserve created_at DESC
        k = _gkey(r)
        if k != last_key:
            grouped_rows.append({
                "is_group_header": True,
                "business_id": k[0],
                "period_type": k[1],
                "created_by_user_id": k[2],
                "created_at_sec": k[3],
                "header_request_id": None,  # will fill below
            })
            last_key = k
        grouped_rows.append(r)

    # --------- Reorder children in each group: FTR first → then PAID (both newest-first) ---------
    # Also set header_request_id to the first child after reordering.
    n = len(grouped_rows)
    i = 0
    while i < n:
        row = grouped_rows[i]
        if row.get("is_group_header"):
            header = row
            children = []
            j = i + 1
            while j < n and not grouped_rows[j].get("is_group_header"):
                child = grouped_rows[j]
                same_group = (
                    child.get("business_id") == header.get("business_id")
                    and (child.get("period_type") or "").upper() == (header.get("period_type") or "")
                )
                if not same_group:
                    break
                children.append(child)
                j += 1

            if children:
                # priority: FTR (id=8) first, then by created_at (newer first); PAID (id=9) after FTR, newer first
                def _key(c):
                    is_ftr = 0 if c.get("request_status_id") == 8 else 1
                    created = -_epoch(c.get("created_at"))  # newer first
                    return (is_ftr, created)

                children_sorted = sorted(children, key=_key)
                grouped_rows[i + 1 : j] = children_sorted
                header["header_request_id"] = children_sorted[0].get("renewal_request_id")
            else:
                header["header_request_id"] = None

            i = j
            continue
        i += 1
    # -------------------------------------------------------------------------------

    # paginate the final list (headers + rows)
    paginator = Paginator(grouped_rows, per_page)
    try:
        page_num = int(request.GET.get("page", "1") or "1")
    except Exception:
        page_num = 1
    if page_num < 1:
        page_num = 1
    if paginator.num_pages >= 1 and page_num > paginator.num_pages:
        page_num = paginator.num_pages
    try:
        page_obj = paginator.page(page_num)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)
    period_type_all = sorted({(r.get("period_type") or "").upper() for r in rows if r and not r.get("is_group_header") and r.get("period_type")})
    year_all = sorted({int(r.get("period_year")) for r in rows if r and not r.get("is_group_header") and r.get("period_year")}, reverse=True)

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Business Renewal',
        'page_title': 'Business Renewal',
        "q": q or "",
        "per_page": per_page,
        "period_types": period_types,
        "paid_filters": paid_filters,  # "paid" -> PAID; "unpaid" -> FTR (alias)
        "year": year,
        "period_type_all": period_type_all,
        "year_all": year_all,
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_numbers": page_numbers,
        "is_paginated": paginator.num_pages > 1,
    }
    return render(request, "treasurer/business_renewal.html", ctx)


# ---------- BUSINESS RENEWAL DETAIL ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_renewal_detail(request: HttpRequest, renewal_request_id: int):
    res = (supabase.table("renewal_request")
           .select("*")
           .eq("renewal_request_id", renewal_request_id)
           .single()
           .execute())
    if getattr(res, "error", None) or not res.data:
        messages.error(request, "Renewal request not found.")
        return redirect("treasurer:business_renewal")

    r = res.data
    STATUS_ID_MAP = {8: "FOR_TREASURER_REVIEW", 9: "PAID"}
    status_name = "PAID" if r.get("paid_on") else STATUS_ID_MAP.get(r.get("request_status_id"), "—")
    status_ui = STATUS_UI.get(status_name) or {"label": status_name, "cls": "badge text-bg-secondary"}

    ptype = (r.get("period_type") or "").upper()
    yr = r.get("period_year")
    qtr = r.get("period_quarter")
    if ptype == "QUARTERLY":
        period_label = f"Q{qtr} {yr}" if (yr and qtr) else (ptype or "—")
    else:
        period_label = str(yr or "—")

    def _f(x):
        try:
            return float(x)
        except Exception:
            return None

    r["base_fee_quote_f"] = _f(r.get("base_fee_quote"))
    r["surcharge_quote_f"] = _f(r.get("surcharge_quote"))
    r["total_quote_f"] = _f(r.get("total_quote"))
    r["period_label"] = period_label

    biz = {}
    try:
        biz_res = supabase.rpc("get_business_details", {"p_business_id": r["business_id"]}).execute()
        if getattr(biz_res, "data", None):
            biz = (biz_res.data[0] if isinstance(biz_res.data, list) else biz_res.data) or {}
    except Exception:
        biz = {}

    # Payment methods (and WAIVED id) - mirror behavior from detail view
    try:
        payment_methods = list_payment_methods()
    except Exception:
        payment_methods = []

    waived_method_id = next(
        (m.get("payment_method_id") for m in (payment_methods or [])
         if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # Expose a payments-like dict to the template (uses renewal fields when available)
    payments = {
        "latest_or_number": r.get("or_number") or "",
        "latest_or_time": r.get("paid_on"),
        "total_paid": r.get("amount_paid") or None,
    }

    # Status and paid flags (mirroring detail view logic)
    def _to_f(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    amount_due = _to_f(r.get("total_quote_f") or r.get("total_quote"))
    total_paid = _to_f(payments.get("total_paid"))
    latest_or = payments.get("latest_or_number") or ""
    status = (status_name or "").upper()

    is_paid_no_or = ((status == "PAID") or (total_paid >= amount_due)) and (latest_or == "")
    is_paid = bool(latest_or) or (status == "PAID") or is_paid_no_or

    # Attach status name to renewal for template checks
    r["status"] = status_name

    user_role = _auth_role_name(request)
    context = {
        'page_path': f'{user_role} / Renewal Detail',
        'page_title': 'Renewal Detail',
        "renewal": r,
        "status_ui": status_ui,
        "biz": biz,
        "payment_methods": payment_methods,
        "waived_method_id": waived_method_id,
        "payments": payments,
        # expose as 'methods' so template code copied from detail.html still works
        "methods": payment_methods,
        "timeline": [],
        "is_paid_no_or": is_paid_no_or,
        "is_paid": is_paid,
        "paid_method_label": None,
        "doc_request_id": None,
        "refunds_all": [],
        "refunds_pending": [],
        "latest_pending_refund": None,
        "has_pending_refund": False,
        "last_completed_refund": None,
    }

    return render(request, "treasurer/business_renewal_details.html", context)


# ---------- BUSINESS RENEWAL (GROUP / PAY-ALL) ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_renewal_group(request: HttpRequest, business_id: int):
    """
    Shows all renewal items (unpaid + paid) for a Business in one page,
    and includes the Pay-All-Unpaid card (moved from detail page).
    """

    # Fetch all renewals for this business (newest first)
    res = (
        supabase.table("renewal_request")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = res.data or []

    # Business snapshot (best-effort)
    try:
        biz_res = supabase.rpc("get_business_details", {"p_business_id": business_id}).execute()
        biz = (biz_res.data[0] if isinstance(biz_res.data, list) else biz_res.data) or {}
    except Exception:
        biz = {}

    # Payment methods (+ WAIVED id)
    try:
        payment_methods = list_payment_methods()
    except Exception:
        payment_methods = []

    waived_method_id = next(
        (m.get("payment_method_id") for m in (payment_methods or [])
         if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # ---------- small helpers ----------
    def _fnum(v):
        try:
            return float(v)
        except Exception:
            return 0.0

    def _period_label(r):
        ptype = (r.get("period_type") or "").upper()
        yr = r.get("period_year")
        qtr = r.get("period_quarter")
        if ptype == "QUARTERLY":
            return f"Q{qtr} {yr}" if (yr and qtr) else (ptype or "—")
        return str(yr or "—")

    def _fmt_iso_local(ts):
        """Return local date string YYYY-MM-DD for a timestamp/ISO string."""
        if not ts:
            return None
        dt = parse_datetime(str(ts))
        if not dt:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.utc)
        return timezone.localtime(dt).strftime("%Y-%m-%d")
    # -----------------------------------

    # Decorate, then split to unpaid / paid
    unpaid, paid = [], []
    for r in rows:
        r["period_label"] = _period_label(r)
        r["base_fee_quote_f"] = _fnum(r.get("base_fee_quote"))
        r["surcharge_quote_f"] = _fnum(r.get("surcharge_quote"))
        r["total_quote_f"] = _fnum(r.get("total_quote"))

        if r.get("request_status_id") == 9:  # PAID
            paid.append(r)
        else:
            unpaid.append(r)

    # Build "preview-like" breakdown from UNPAID items
    quote_rows, base_sum, surch_sum, grand_total = [], 0.0, 0.0, 0.0
    for r in unpaid:
        # heuristic for CURRENT vs ARREARS
        deadline = r.get("deadline") or r.get("due_date")  # support either column
        kind = "CURRENT"
        try:
            d = parse_datetime(str(deadline))
            if d:
                if timezone.is_naive(d):
                    d = timezone.make_aware(d, timezone.utc)
                if timezone.localtime(d).date() < timezone.localdate():
                    kind = "ARREARS"
        except Exception:
            pass

        line = {
            "item_year": r.get("period_year"),
            "kind": kind,
            "base_fee": r.get("base_fee_quote_f") or 0.0,
            "offense_no": r.get("offense_no") or None,
            "surcharge": r.get("surcharge_quote_f") or 0.0,
            "total": r.get("total_quote_f") or 0.0,
            "deadline": deadline,
            "days_late": r.get("days_late") or None,
            "renewal_request_id": r.get("renewal_request_id"),
            "period_label": r.get("period_label"),
        }
        base_sum += line["base_fee"]
        surch_sum += line["surcharge"]
        grand_total += line["total"]
        quote_rows.append(line)

    # Paid history rows (now with formatted paid_on)
    paid_rows = []
    for r in paid:
        paid_rows.append({
            "period_year": r.get("period_year"),
            "or_number": r.get("or_number"),
            "paid_on": r.get("paid_on"),
            "paid_on_disp": _fmt_iso_local(r.get("paid_on")),  # <-- formatted here
            "period_label": r.get("period_label"),
            "total_paid": r.get("amount_paid") or r.get("total_quote_f"),
        })

    # Defaults for the Pay-All form
    try:
        latest_unpaid_year = max([x.get("period_year") for x in unpaid if x.get("period_year")], default=None)
    except Exception:
        latest_unpaid_year = None

    has_quarterly = any((r.get("period_type") or "").upper() == "QUARTERLY" for r in rows)
    default_period_type = "QUARTERLY" if has_quarterly else "ANNUAL"

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Renewal Group',
        'page_title': 'Renewal Group',
        "biz": biz,
        "business_id": business_id,
        "quote_rows": quote_rows,
        "paid_rows": paid_rows,
        "base_sum": base_sum,
        "surch_sum": surch_sum,
        "grand_total": grand_total,
        "payment_methods": payment_methods,
        "methods": payment_methods,          # alias for template reuse
        "waived_method_id": waived_method_id,
        "default_period_type": default_period_type,
        "default_year": latest_unpaid_year or timezone.now().year,
    }
    return render(request, "treasurer/business_renewal_group.html", ctx)

@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def business_renewal_recalc(request: HttpRequest, renewal_request_id: int):
    asof_str = (request.POST.get("asof_date") or "").strip()
    asof_date = parse_date(asof_str) or date.today()

    try:
        res = supabase.rpc("renewal_preview_recalculate", {
            "p_renewal_request_id": int(renewal_request_id),
            "p_asof_date": asof_date.isoformat(),
        }).execute()
        if getattr(res, "error", None):
            raise RuntimeError(getattr(res.error, "message", "RPC error"))
    except Exception as e:
        messages.error(request, f"Recalculate failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)

    row = (res.data or {}) if isinstance(res.data, dict) else (res.data[0] if res.data else {})
    try:
        base = float(row.get("base_fee_quote", 0) or 0)
        sur = float(row.get("surcharge_quote", 0) or 0)
        tot = float(row.get("total_quote", 0) or 0)
        messages.success(request, f"Preview updated — Base ₱{base:,.2f}, Surcharge ₱{sur:,.2f}, Total ₱{tot:,.2f}.")
    except Exception:
        messages.success(request, "Preview updated.")
    return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)


# ========= CONFIRM & POST OR (online paid, no OR yet) =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def confirm_post_or(request: HttpRequest, doc_request_id: int):
    """
    - Uses RPC treasurer_confirm_and_post_or to:
      * create OR (uses supplied OR number, or auto-generate)
      * mark PAID and advance to FOR_PRINTING
      * log OR_ISSUED / STATUS_CHANGED timeline
    - Default payment method is Online GCash (id=5)
    """
    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session required.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    or_number = (request.POST.get("or_number") or "").strip() or None
    # Let the DB default this to 5, but we still pass 5 so the UI intent is clear.
    payment_method_id = int(request.POST.get("payment_method_id", "5") or "5") or 5

    try:
        or_id = confirm_and_post_or(
            doc_request_id=doc_request_id,
            staff_id=staff_id,
            or_number=or_number,
            payment_method_id=payment_method_id,
        )
    except Exception as e:
        messages.error(request, f"Confirm & Post OR failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    try:
        or_res = (supabase.table("official_receipt")
                  .select("or_number, amount_paid, amount_due")
                  .eq("or_id", or_id).single().execute())
        if getattr(or_res, "data", None):
            o = or_res.data
            messages.success(request, f"OR {o.get('or_number','—')} posted (₱{float(o.get('amount_paid',0) or 0):,.2f}).")
        else:
            messages.success(request, f"OR posted (id {or_id}).")
    except Exception:
        messages.success(request, f"OR posted (id {or_id}).")

    messages.info(request, "Request moved to FOR_PRINTING.")
    return redirect("treasurer:detail", doc_request_id=doc_request_id)


# ========= BUSINESS RENEWAL: TAKE PAYMENT =========

@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def business_renewal_take_payment(request: HttpRequest, renewal_request_id: int):
    staff_id = _staff_id(request) or 0
    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
    except Exception:
        method_id = 0
    # amount is ignored by RPC; allow 0, block negatives
    try:
        amount_paid = float(request.POST.get("amount_paid", "0") or 0)
    except Exception:
        amount_paid = 0.0

    or_number = (request.POST.get("or_number") or None)
    paid_on   = (request.POST.get("paid_on") or None)

    if staff_id <= 0 or method_id <= 0 or amount_paid < 0:
        messages.error(request, "Select a payment method and ensure your staff session is active.")
        return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)

    # Get the linked document request ID if it exists
    doc_request_id = None
    try:
        renewal_res = supabase.table("renewal_request").select("doc_request_id, business_id").eq("renewal_request_id", renewal_request_id).single().execute()
        if renewal_res.data:
            doc_request_id = renewal_res.data.get("doc_request_id")
            business_id_from_renewal = renewal_res.data.get("business_id")
    except Exception:
        pass
    
    # If there's a document request, process payment through normal document flow
    if doc_request_id:
        try:
            or_id = accept_payment(
                doc_request_id=doc_request_id,
                method_id=method_id,
                amount_paid=float(amount_paid),
                staff_id=staff_id,
            )
            
            # Update renewal_request to PAID status
            supabase.table("renewal_request").update({
                "request_status_id": 9,  # PAID
                "paid_on": paid_on or supabase.now(),
                "or_number": or_number,
                "amount_paid": amount_paid,
            }).eq("renewal_request_id", renewal_request_id).execute()
            
            # Move to FOR_PRINTING
            try:
                mark_for_printing(doc_request_id=doc_request_id, staff_id=staff_id, reason="Auto-marked after renewal payment")
            except Exception:
                pass
                
        except Exception as e:
            messages.error(request, f"Payment failed: {escape(str(getattr(e, 'message', e)))}")
            return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)
    else:
        # Fallback to old direct clearance creation method
        try:
            from .services.payments_service import accept_renewal_payment
            clearance_id = accept_renewal_payment(
                renewal_request_id=int(renewal_request_id),
                method_id=method_id,
                amount_paid=amount_paid,
                staff_id=staff_id,
                or_number=or_number,
                paid_on=paid_on,
            )
        except Exception as e:
            messages.error(request, f"Payment failed: {escape(str(getattr(e, 'message', e)))}")
            return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)

    # Send notifications after successful payment
    try:
        # Get renewal request details to extract business_id
        res = supabase.table("renewal_request").select("*").eq("renewal_request_id", renewal_request_id).single().execute()
        if res.data:
            business_id = res.data.get("business_id")
            period_type = res.data.get("period_type", "")
            period_year = res.data.get("period_year", "")
            
            # Log business action
            try:
                log_business_action(
                    business_id=business_id,
                    table_affected='RENEWAL_PAYMENT',
                    action='UPDATE',
                    performer_id=staff_id,
                    details=f'Accepted renewal payment for business #{business_id}, period: {period_type} {period_year}',
                )
            except Exception:
                pass
            
            # Get business and owner info
            business_info = AppContainer.owner_business_service()
            dto = business_info.execute_by_business_id(business_id)
            owner = dict(dto.owner or {})
            business = dict(dto.business or {})
            
            owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
            owner_email = (owner.get("email") or "").strip()
            owner_person_id = owner.get("person_id") or owner.get("owner_person_id")
            bname = (business.get("business_name") or "your business").strip()
            
            # Send SMS
            if owner_mobile:
                msg = (
                    f"BARUG: Payment received for business renewal '{bname}'.\n"
                    f"Period: {period_type} {period_year}. Status: PAID.\n"
                    f"Your business clearance is now ready."
                )
                send_sms(owner_mobile, msg, fail_silently=True)
            
            # Send Email
            if owner_email:
                try:
                    owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip() or "Business Owner"
                    subject = f"Business Renewal Payment Confirmed - {bname}"
                    body_html = f"""
                        <p>Hi {owner_name},</p>
                        <p>Your payment for business renewal has been received and confirmed for <strong>{bname}</strong> (ID: {business_id:06d}).</p>
                        <p><b>Period:</b> {period_type} {period_year}</p>
                        <p><b>Status:</b> PAID</p>
                        <p>Your business clearance is now ready. Thank you for your prompt payment.</p>
                        <p>Thank you,<br>Barangay Sto. Niño</p>
                    """
                    body_txt = (
                        f"Hi {owner_name},\n\n"
                        f"Your payment for business renewal has been received and confirmed for {bname} (ID: {business_id:06d}).\n"
                        f"Period: {period_type} {period_year}\n"
                        f"Status: PAID\n\n"
                        f"Your business clearance is now ready. Thank you for your prompt payment.\n\n"
                        f"Thank you,\nBarangay Sto. Niño\n"
                    )
                    send_email(
                        subject=subject,
                        to=[(owner_name, owner_email)],
                        body_text=body_txt,
                        body_html=body_html,
                        from_name="Barangay Sto. Niño",
                        fail_silently=True,
                    )
                except Exception:
                    pass
            
            # Send in-app notification
            if owner_person_id:
                try:
                    notify_user(
                        user_type_id=1,  # PERSON
                        person_id=owner_person_id,
                        staff_id=None,
                        title="Business Renewal Payment Confirmed",
                        body=f"Payment received for '{bname}' renewal. Period: {period_type} {period_year}. Your clearance is ready.",
                        deep_link=f"/business/{business_id}"
                    )
                except Exception:
                    pass
    except Exception:
        pass

    messages.success(request, f"Payment posted (clearance id {clearance_id}).")
    return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)

@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def business_renewal_take_payment_all(request: HttpRequest, business_id: int):
    staff_id = _staff_id(request) or 0
    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
    except Exception:
        method_id = 0

    period_type = (request.POST.get("period_type") or "ANNUAL").upper()
    try:
        period_year = int(request.POST.get("period_year"))
    except Exception:
        from datetime import date
        period_year = date.today().year

    paid_on = (request.POST.get("paid_on") or None)

    if staff_id <= 0 or method_id <= 0:
        messages.error(request, "Select a payment method and ensure your staff session is active.")
        return redirect("treasurer:business_renewal_detail", b_id=business_id)

    # Check if there are any renewal requests with linked document requests
    has_doc_requests = False
    try:
        check_res = supabase.table("renewal_request").select("doc_request_id").eq("business_id", business_id).eq("request_status_id", 8).not_.is_("doc_request_id", "null").limit(1).execute()
        has_doc_requests = bool(check_res.data)
    except Exception:
        pass

    if has_doc_requests:
        # Process each unpaid renewal with a document request
        try:
            unpaid_renewals = supabase.table("renewal_request").select("renewal_request_id, doc_request_id, business_id, period_type, period_year").eq("business_id", business_id).eq("request_status_id", 8).not_.is_("doc_request_id", "null").eq("period_type", period_type).lte("period_year", period_year).execute()
            
            cnt = 0
            for renewal in (unpaid_renewals.data or []):
                doc_req_id = renewal.get("doc_request_id")
                renewal_id = renewal.get("renewal_request_id")
                
                if doc_req_id:
                    try:
                        # Accept payment for document request
                        or_id = accept_payment(
                            doc_request_id=doc_req_id,
                            method_id=method_id,
                            amount_paid=0,  # Amount calculated by RPC
                            staff_id=staff_id,
                        )
                        
                        # Update renewal to PAID
                        supabase.table("renewal_request").update({
                            "request_status_id": 9,
                            "paid_on": paid_on or supabase.now(),
                            "amount_paid": 0,  # Will be set by trigger
                        }).eq("renewal_request_id", renewal_id).execute()
                        
                        # Mark for printing
                        try:
                            mark_for_printing(doc_request_id=doc_req_id, staff_id=staff_id, reason="Auto-marked after bulk renewal payment")
                        except Exception:
                            pass
                        
                        cnt += 1
                    except Exception as e:
                        print(f"Failed to process renewal {renewal_id}: {e}")
            
            if cnt > 0:
                # Log business action
                try:
                    log_business_action(
                        business_id=business_id,
                        table_affected='RENEWAL_PAYMENT',
                        action='UPDATE',
                        performer_id=staff_id,
                        details=f'Accepted {cnt} renewal payment(s) for business #{business_id}',
                    )
                except Exception:
                    pass
                
                # Send notifications
                try:
                    business_info = AppContainer.owner_business_service()
                    dto = business_info.execute_by_business_id(business_id)
                    owner = dict(dto.owner or {})
                    business = dict(dto.business or {})
                    
                    owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
                    owner_email = (owner.get("email") or "").strip()
                    owner_person_id = owner.get("person_id") or owner.get("owner_person_id")
                    bname = (business.get("business_name") or "your business").strip()
                    
                    if owner_mobile:
                        msg = (
                            f"BARUG: Payment received for business renewal '{bname}'.\n"
                            f"{cnt} year(s) paid.\n"
                            f"Your business clearance is now ready."
                        )
                        send_sms(owner_mobile, msg, fail_silently=True)
                    
                    if owner_email:
                        try:
                            owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip() or "Business Owner"
                            subject = f"Business Renewal Payment Confirmed - {bname}"
                            body_html = f"""
                                <p>Hi {owner_name},</p>
                                <p>Your payment for business renewal has been received and confirmed for <strong>{bname}</strong> (ID: {business_id:06d}).</p>
                                <p><b>Years Paid:</b> {cnt}</p>
                                <p><b>Status:</b> PAID</p>
                                <p>Your business clearance is now ready. Thank you for your prompt payment.</p>
                                <p>Thank you,<br>Barangay Sto. Niño</p>
                            """
                            body_txt = (
                                f"Hi {owner_name},\n\n"
                                f"Your payment for business renewal has been received and confirmed for {bname} (ID: {business_id:06d}).\n"
                                f"Years Paid: {cnt}\n"
                                f"Status: PAID\n\n"
                                f"Your business clearance is now ready. Thank you for your prompt payment.\n\n"
                                f"Thank you,\nBarangay Sto. Niño\n"
                            )
                            send_email(
                                subject=subject,
                                to=[(owner_name, owner_email)],
                                body_text=body_txt,
                                body_html=body_html,
                                from_name="Barangay Sto. Niño",
                                fail_silently=True,
                            )
                        except Exception:
                            pass
                    
                    if owner_person_id:
                        try:
                            notify_user(
                                user_type_id=1,
                                person_id=owner_person_id,
                                staff_id=None,
                                title="Business Renewal Payment Confirmed",
                                body=f"Payment received for '{bname}' renewal. {cnt} year(s) paid. Your clearance is ready.",
                                deep_link=f"/business/{business_id}"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
                
                messages.success(request, f"Accepted payments for {cnt} unpaid year(s).")
            else:
                messages.info(request, "No unpaid items found.")
                
        except Exception as e:
            messages.error(request, f"Bulk payment failed: {escape(str(getattr(e, 'message', e)))}")
    else:
        # Fallback to old direct clearance method
        try:
            from .services.payments_service import accept_all_unpaid_payments
            summary = accept_all_unpaid_payments(
                business_id=business_id,
                period_type=period_type,
                period_year=period_year,
                method_id=method_id,
                staff_id=staff_id,
                paid_on=paid_on,
            )
            cnt   = (summary or {}).get("processed_count", 0)
            total = (summary or {}).get("sum_quoted_total", "0")
            
            # Log business action
            if cnt > 0:
                try:
                    log_business_action(
                        business_id=business_id,
                        table_affected='RENEWAL_PAYMENT',
                        action='UPDATE',
                        performer_id=staff_id,
                        details=f'Accepted {cnt} renewal payment(s) for business #{business_id}, total: {total}',
                    )
                except Exception:
                    pass
            
            # Send notifications after successful bulk payment
            if cnt > 0:
                try:
                    business_info = AppContainer.owner_business_service()
                    dto = business_info.execute_by_business_id(business_id)
                    owner = dict(dto.owner or {})
                    business = dict(dto.business or {})
                    
                    owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
                    owner_email = (owner.get("email") or "").strip()
                    owner_person_id = owner.get("person_id") or owner.get("owner_person_id")
                    bname = (business.get("business_name") or "your business").strip()
                    
                    # Send SMS
                    if owner_mobile:
                        msg = (
                            f"BARUG: Payment received for business renewal '{bname}'.\n"
                            f"{cnt} year(s) paid. Total: {total}.\n"
                            f"Your business clearance is now ready."
                        )
                        send_sms(owner_mobile, msg, fail_silently=True)
                    
                    # Send Email
                    if owner_email:
                        try:
                            owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip() or "Business Owner"
                            subject = f"Business Renewal Payment Confirmed - {bname}"
                            body_html = f"""
                            <p>Hi {owner_name},</p>
                            <p>Your payment for business renewal has been received and confirmed for <strong>{bname}</strong> (ID: {business_id:06d}).</p>
                            <p><b>Years Paid:</b> {cnt}</p>
                            <p><b>Total Amount:</b> {total}</p>
                            <p><b>Status:</b> PAID</p>
                            <p>Your business clearance is now ready. Thank you for your prompt payment.</p>
                            <p>Thank you,<br>Barangay Sto. Niño</p>
                        """
                            body_txt = (
                                f"Hi {owner_name},\n\n"
                                f"Your payment for business renewal has been received and confirmed for {bname} (ID: {business_id:06d}).\n"
                                f"Years Paid: {cnt}\n"
                                f"Total Amount: {total}\n"
                                f"Status: PAID\n\n"
                                f"Your business clearance is now ready. Thank you for your prompt payment.\n\n"
                                f"Thank you,\nBarangay Sto. Niño\n"
                            )
                            send_email(
                                subject=subject,
                                to=[(owner_name, owner_email)],
                                body_text=body_txt,
                                body_html=body_html,
                                from_name="Barangay Sto. Niño",
                                fail_silently=True,
                            )
                        except Exception:
                            pass
                    
                    # Send in-app notification
                    if owner_person_id:
                        try:
                            notify_user(
                                user_type_id=1,  # PERSON
                                person_id=owner_person_id,
                                staff_id=None,
                                title="Business Renewal Payment Confirmed",
                                body=f"Payment received for '{bname}' renewal. {cnt} year(s) paid. Total: {total}. Your clearance is ready.",
                                deep_link=f"/business/{business_id}"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
            
            messages.success(request, f"Accepted payments for {cnt} unpaid year(s). Total due: {total}.")
        except Exception as e:
            messages.error(request, f"Bulk payment failed: {escape(str(getattr(e, 'message', e)))}")
    
    return redirect("treasurer:business_renewal_group", business_id=business_id)

# ========= CLOSURE =========
STATUS_ID_MAP = {8: "FOR_TREASURER_REVIEW", 9: "PAID"} 

def _fmt_iso_local(ts):
    if not ts:
        return None
    dt = parse_datetime(str(ts))
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")

def _epoch(ts) -> float:
    dt = parse_datetime(str(ts)) if ts else None
    if not dt:
        return 0.0
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt.timestamp()

def _fnum(v):
    try:
        return float(v)
    except Exception:
        return None

# ---------- CLOSURE LIST ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def closure_list(request):
    q = (request.GET.get("q") or "").strip() or None
    period_types = [p.strip().upper() for p in request.GET.getlist("period_type") if p.strip()]
    year = (request.GET.get("year") or "").strip()
    paid_filters = [p.strip().lower() for p in request.GET.getlist("paid") if p.strip()]
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 10
    if per_page not in (5, 10, 25, 50):
        per_page = 10

    query = supabase.table("closure_payment_request").select("*").order("created_at", desc=True)

    if q:
        or_parts = [f"request_code.ilike.%{q}%", f"or_number.ilike.%{q}%"]
        if q.isdigit():
            or_parts += [f"period_year.eq.{q}", f"business_id.eq.{q}"]
        query = query.or_(",".join(or_parts))

    if year.isdigit():
        query = query.eq("period_year", int(year))
    if period_types:
        query = query.in_("period_type", period_types)

    res = query.limit(500).execute()
    rows = res.data or []

    if paid_filters:
        want_paid = "paid" in paid_filters and "unpaid" not in paid_filters
        want_unpaid = "unpaid" in paid_filters and "paid" not in paid_filters
        if want_paid:
            rows = [r for r in rows if r.get("request_status_id") == 9]
        elif want_unpaid:
            rows = [r for r in rows if r.get("request_status_id") == 8]

    # decorate
    for r in rows:
        status_name = STATUS_ID_MAP.get(r.get("request_status_id"), "—")
        ui = STATUS_UI.get(status_name) or {"label": status_name, "cls": "badge text-bg-secondary"}
        r["status_name"] = status_name
        r["status_ui"] = ui

        ptype = (r.get("period_type") or "").upper()
        yr = r.get("period_year")
        qtr = r.get("period_quarter")
        r["period_label"] = (f"Q{qtr} {yr}" if (ptype == "QUARTERLY" and yr and qtr) else str(yr or "—"))
        r["base_fee_quote_f"] = _fnum(r.get("base_fee_quote"))
        r["surcharge_quote_f"] = _fnum(r.get("surcharge_quote"))
        r["total_quote_f"] = _fnum(r.get("total_quote"))
        r["paid_on_disp"] = _fmt_iso_local(r.get("paid_on"))

    # grouping (same approach as renewal)
    def _gkey(r):
        return (r.get("business_id"), (r.get("period_type") or "").upper(), r.get("created_by_user_id"), str(r.get("created_at") or "")[:19])

    grouped_rows, last_key = [], None
    for r in rows:
        k = _gkey(r)
        if k != last_key:
            grouped_rows.append({
                "is_group_header": True,
                "business_id": k[0],
                "period_type": k[1],
                "created_by_user_id": k[2],
                "created_at_sec": k[3],
            })
            last_key = k
        grouped_rows.append(r)

    # reorder children: FTR first, then PAID (newest-first each)
    n, i = len(grouped_rows), 0
    while i < n:
        row = grouped_rows[i]
        if row.get("is_group_header"):
            header, children, j = row, [], i + 1
            while j < n and not grouped_rows[j].get("is_group_header"):
                child = grouped_rows[j]
                same_group = (child.get("business_id") == header.get("business_id")
                              and (child.get("period_type") or "").upper() == (header.get("period_type") or ""))
                if not same_group:
                    break
                children.append(child)
                j += 1
            if children:
                def _key(c):
                    is_ftr = 0 if c.get("request_status_id") == 8 else 1
                    created = -_epoch(c.get("created_at"))
                    return (is_ftr, created)
                grouped_rows[i + 1 : j] = sorted(children, key=_key)
            i = j
            continue
        i += 1

    paginator = Paginator(grouped_rows, per_page)
    try:
        page_num = int(request.GET.get("page", "1") or "1")
    except Exception:
        page_num = 1
    if page_num < 1:
        page_num = 1
    if paginator.num_pages and page_num > paginator.num_pages:
        page_num = paginator.num_pages
    try:
        page_obj = paginator.page(page_num)
    except EmptyPage:
        page_obj = paginator.page(1)

    # derivations for filter panels
    def build_page_numbers(cur, pages, window=2):
        nums = []
        for p in range(1, pages + 1):
            if p in (1, pages) or abs(p - cur) <= window:
                nums.append(p)
            elif nums and nums[-1] is not None:
                nums.append(None)
        return nums

    period_type_all = sorted({(r.get("period_type") or "").upper()
                              for r in rows if r and not r.get("is_group_header") and r.get("period_type")})
    year_all = sorted({int(r.get("period_year"))
                       for r in rows if r and not r.get("is_group_header") and r.get("period_year")}, reverse=True)

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Closure List',
        'page_title': 'Closure List',
        "q": q or "",
        "per_page": per_page,
        "period_types": period_types,
        "paid_filters": paid_filters,
        "year": year,
        "period_type_all": period_type_all,
        "year_all": year_all,
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_numbers": build_page_numbers(page_obj.number, paginator.num_pages),
        "is_paginated": paginator.num_pages > 1,
    }
    return render(request, "treasurer/closure_list.html", ctx)


# ---------- CLOSURE DETAIL ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def closure_detail(request, closure_payment_request_id: int):
    res = (supabase.table("closure_payment_request")
           .select("*")
           .eq("closure_payment_request_id", closure_payment_request_id)
           .single()
           .execute())
    if getattr(res, "error", None) or not res.data:
        messages.error(request, "Closure payment request not found.")
        return redirect("treasurer:closure_list")

    r = res.data
    status_name = "PAID" if r.get("paid_on") else STATUS_ID_MAP.get(r.get("request_status_id"), "—")
    status_ui = STATUS_UI.get(status_name) or {"label": status_name, "cls": "badge text-bg-secondary"}

    ptype = (r.get("period_type") or "").upper()
    yr = r.get("period_year")
    qtr = r.get("period_quarter")
    period_label = f"Q{qtr} {yr}" if (ptype == "QUARTERLY" and yr and qtr) else str(yr or "—")

    r["base_fee_quote_f"] = _fnum(r.get("base_fee_quote"))
    r["surcharge_quote_f"] = _fnum(r.get("surcharge_quote"))
    r["total_quote_f"] = _fnum(r.get("total_quote"))
    r["period_label"] = period_label
    r["status"] = status_name

    # Business snapshot (best-effort)
    try:
        biz_res = supabase.rpc("get_business_details", {"p_business_id": r["business_id"]}).execute()
        biz = (biz_res.data[0] if isinstance(biz_res.data, list) else biz_res.data) or {}
    except Exception:
        biz = {}

    try:
        payment_methods = list_payment_methods()
        cash_method = next((m for m in payment_methods if m.get("method_name") == "CASH"), None)
        cash_payment_method_id = cash_method.get("payment_method_id") if cash_method else (payment_methods[0].get("payment_method_id") if payment_methods else 1)
    except Exception:
        payment_methods = []
        cash_payment_method_id = 1  # fallback to ID 1

    payments = {
        "latest_or_number": r.get("or_number") or "",
        "latest_or_time": r.get("paid_on"),
        "total_paid": r.get("total_quote") or r.get("base_fee_quote"),
    }

    # Controls visibility
    def _to_f(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    amount_due = _to_f(r.get("total_quote_f") or r.get("total_quote"))
    total_paid = _to_f(payments.get("total_paid"))
    latest_or = payments.get("latest_or_number") or ""
    status = (status_name or "").upper()
    is_paid_no_or = ((status == "PAID") or (total_paid >= amount_due)) and (latest_or == "")
    is_paid = bool(latest_or) or (status == "PAID") or is_paid_no_or

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Closure Detail',
        'page_title': 'Closure Detail',
        "item": r,
        "status_ui": status_ui,
        "biz": biz,
        "payment_methods": payment_methods,
        "methods": payment_methods,
        "payments": payments,
        "is_paid_no_or": is_paid_no_or,
        "is_paid": is_paid,
        "today": timezone.now().date().isoformat(),
        "cash_payment_method_id": cash_payment_method_id,
    }
    return render(request, "treasurer/closure_detail.html", ctx)


# ---------- POST: Take single payment ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def closure_take_payment(request, closure_payment_request_id: int):
    method_id = int(request.POST.get("payment_method_id"))
    amount_paid = request.POST.get("amount_paid")  # not used by RPC; kept for symmetry
    or_number = request.POST.get("or_number") or None
    paid_on = request.POST.get("paid_on") or None

    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        messages.error(request, "Session expired.")
        return redirect("treasurer:closure_detail", closure_payment_request_id=closure_payment_request_id)

    try:
        payload = {
            "p_closure_payment_request_id": int(closure_payment_request_id),
            "p_payment_method_id": int(method_id),
            "p_received_by_staff_id": int(staff_id),
            "p_paid_on": paid_on,
            "p_or_number": or_number,
        }
        res = supabase.rpc("treasurer_accept_closure_payment_h", payload).execute()
        if getattr(res, "error", None):
            raise RuntimeError(getattr(res.error, "message", str(res.error)))
        
        # Log business action
        try:
            closure_res = supabase.table("closure_payment_request").select("business_id").eq("closure_payment_request_id", closure_payment_request_id).single().execute()
            if closure_res.data:
                business_id = closure_res.data.get("business_id")
                log_business_action(
                    business_id=business_id,
                    table_affected='CLOSURE_PAYMENT',
                    action='UPDATE',
                    performer_id=staff_id,
                    details=f'Accepted closure payment for business #{business_id}, request #{closure_payment_request_id}',
                )
        except Exception:
            pass
        
        # Send notifications after successful closure payment
        try:
            # Get closure request details to extract business_id
            closure_res = supabase.table("closure_payment_request").select("*").eq("closure_payment_request_id", closure_payment_request_id).single().execute()
            if closure_res.data:
                business_id = closure_res.data.get("business_id")
                period_type = closure_res.data.get("period_type", "")
                period_year = closure_res.data.get("period_year", "")
                
                # Get business and owner info
                business_info = AppContainer.owner_business_service()
                dto = business_info.execute_by_business_id(business_id)
                owner = dict(dto.owner or {})
                business = dict(dto.business or {})
                
                owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
                owner_email = (owner.get("email") or "").strip()
                owner_person_id = owner.get("person_id") or owner.get("owner_person_id")
                bname = (business.get("business_name") or "your business").strip()
                
                # Send SMS
                if owner_mobile:
                    msg = (
                        f"BARUG: Business closure payment confirmed for '{bname}'.\n"
                        f"All dues settled. Your business is now officially CLOSED.\n"
                        f"Thank you."
                    )
                    send_sms(owner_mobile, msg, fail_silently=True)
                
                # Send Email
                if owner_email:
                    try:
                        owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip() or "Business Owner"
                        subject = f"Business Closure Confirmed - {bname}"
                        body_html = f"""
                            <p>Hi {owner_name},</p>
                            <p>Your business closure payment has been confirmed for <strong>{bname}</strong> (ID: {business_id:06d}).</p>
                            <p><b>Status:</b> CLOSED</p>
                            <p>All outstanding dues have been settled. Your business is now officially closed.</p>
                            <p>Thank you for your compliance.</p>
                            <p>Thank you,<br>Barangay Sto. Niño</p>
                        """
                        body_txt = (
                            f"Hi {owner_name},\n\n"
                            f"Your business closure payment has been confirmed for {bname} (ID: {business_id:06d}).\n"
                            f"Status: CLOSED\n\n"
                            f"All outstanding dues have been settled. Your business is now officially closed.\n\n"
                            f"Thank you for your compliance.\n\n"
                            f"Thank you,\nBarangay Sto. Niño\n"
                        )
                        send_email(
                            subject=subject,
                            to=[(owner_name, owner_email)],
                            body_text=body_txt,
                            body_html=body_html,
                            from_name="Barangay Sto. Niño",
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                
                # Send in-app notification
                if owner_person_id:
                    try:
                        notify_user(
                            user_type_id=1,  # PERSON
                            person_id=owner_person_id,
                            staff_id=None,
                            title="Business Closure Confirmed",
                            body=f"Closure payment confirmed for '{bname}'. All dues settled. Business status: CLOSED.",
                            deep_link=f"/business/{business_id}"
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        
        messages.success(request, "Closure payment accepted and business set to CLOSED.")
    except Exception as e:
        messages.error(request, f"Failed to accept closure payment: {e}")

    return redirect("treasurer:closure_detail", closure_payment_request_id=closure_payment_request_id)


# ---------- GROUP (Pay-All) ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def closure_group(request, business_id: int):
    res = (
        supabase.table("closure_payment_request")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = res.data or []

    try:
        biz_res = supabase.rpc("get_business_details", {"p_business_id": business_id}).execute()
        biz = (biz_res.data[0] if isinstance(biz_res.data, list) else biz_res.data) or {}
    except Exception:
        biz = {}

    try:
        payment_methods = list_payment_methods()
        cash_method = next((m for m in payment_methods if m.get("method_name") == "CASH"), None)
        cash_payment_method_id = cash_method.get("payment_method_id") if cash_method else (payment_methods[0].get("payment_method_id") if payment_methods else 1)
    except Exception:
        payment_methods = []
        cash_payment_method_id = 1  # fallback to ID 1

    unpaid, paid = [], []
    for r in rows:
        ptype = (r.get("period_type") or "").upper()
        yr = r.get("period_year")
        qtr = r.get("period_quarter")
        r["period_label"] = (f"Q{qtr} {yr}" if (ptype == "QUARTERLY" and yr and qtr) else str(yr or "—"))
        r["base_fee_quote_f"] = _fnum(r.get("base_fee_quote"))
        r["surcharge_quote_f"] = _fnum(r.get("surcharge_quote"))
        r["total_quote_f"] = _fnum(r.get("total_quote"))
        if r.get("request_status_id") == 9:
            paid.append(r)
        else:
            unpaid.append(r)

    quote_rows, base_sum, surch_sum, grand_total = [], 0.0, 0.0, 0.0
    current_year = timezone.now().year
    for r in unpaid:
        year = r.get("period_year")
        kind = "CURRENT" if year == current_year else "ARREARS"
        line = {
            "item_year": year,
            "kind": kind,
            "base_fee": r.get("base_fee_quote_f") or 0.0,
            "offense_no": r.get("offense_no") or None,  # tolerate if present
            "surcharge": r.get("surcharge_quote_f") or 0.0,
            "total": r.get("total_quote_f") or 0.0,
            "period_label": r.get("period_label"),
            "closure_payment_request_id": r.get("closure_payment_request_id"),
        }
        base_sum += line["base_fee"]
        surch_sum += line["surcharge"]
        grand_total += line["total"]
        quote_rows.append(line)

    try:
        latest_unpaid_year = max([x.get("period_year") for x in unpaid if x.get("period_year")], default=None)
    except Exception:
        latest_unpaid_year = None

    has_quarterly = any((r.get("period_type") or "").upper() == "QUARTERLY" for r in rows)
    default_period_type = "QUARTERLY" if has_quarterly else "ANNUAL"

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Closure Group',
        'page_title': 'Closure Group',
        "biz": biz,
        "business_id": business_id,
        "quote_rows": quote_rows,
        "base_sum": base_sum,
        "surch_sum": surch_sum,
        "grand_total": grand_total,
        "payment_methods": payment_methods,
        "methods": payment_methods,
        "default_period_type": default_period_type,
        "default_year": latest_unpaid_year or timezone.now().year,
        "today": timezone.now().date().isoformat(),
        "cash_payment_method_id": cash_payment_method_id,
        "paid_rows": [
            {
                "period_year": r.get("period_year"),
                "period_label": r.get("period_label"),
                "or_number": r.get("or_number"),
                "paid_on_disp": (_fmt_iso_local(r.get("paid_on")) or "—"),
                "total_paid": r.get("total_quote_f") or r.get("total_quote"),
            } for r in paid
        ],
    }
    return render(request, "treasurer/closure_group.html", ctx)


# ---------- POST: Pay all unpaid ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def closure_take_payment_all(request, business_id: int):
    period_type = (request.POST.get("period_type") or "ANNUAL").upper()
    period_year = int(request.POST.get("period_year"))
    method_id = int(request.POST.get("payment_method_id"))
    paid_on = request.POST.get("paid_on") or None

    staff_id = (request.session.get("auth") or {}).get("staff_id")
    if not staff_id:
        messages.error(request, "Session expired.")
        return redirect("treasurer:closure_group", business_id=business_id)

    try:
        payload = {
            "p_business_id": int(business_id),
            "p_period_type": period_type,
            "p_period_year": int(period_year),
            "p_payment_method_id": int(method_id),
            "p_received_by_staff_id": int(staff_id),
            "p_paid_on": paid_on,
        }
        res = supabase.rpc("treasurer_accept_all_unpaid_closure_h", payload).execute()
        if getattr(res, "error", None):
            raise RuntimeError(getattr(res.error, "message", str(res.error)))
        
        # Log business action
        try:
            log_business_action(
                business_id=business_id,
                table_affected='CLOSURE_PAYMENT',
                action='UPDATE',
                performer_id=staff_id,
                details=f'Accepted all unpaid closure payments for business #{business_id}',
            )
        except Exception:
            pass
        
        # Send notifications after successful bulk closure payment
        try:
            business_info = AppContainer.owner_business_service()
            dto = business_info.execute_by_business_id(business_id)
            owner = dict(dto.owner or {})
            business = dict(dto.business or {})
            
            owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
            owner_email = (owner.get("email") or "").strip()
            owner_person_id = owner.get("person_id") or owner.get("owner_person_id")
            bname = (business.get("business_name") or "your business").strip()
            
            # Send SMS
            if owner_mobile:
                msg = (
                    f"BARUG: Business closure payment confirmed for '{bname}'.\n"
                    f"All outstanding dues settled.\n"
                    f"Your business is now officially CLOSED."
                )
                send_sms(owner_mobile, msg, fail_silently=True)
            
            # Send Email
            if owner_email:
                try:
                    owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip() or "Business Owner"
                    subject = f"Business Closure Confirmed - {bname}"
                    body_html = f"""
                        <p>Hi {owner_name},</p>
                        <p>Your business closure payment has been confirmed for <strong>{bname}</strong> (ID: {business_id:06d}).</p>
                        <p><b>Status:</b> CLOSED</p>
                        <p>All outstanding dues have been settled. Your business is now officially closed.</p>
                        <p>Thank you for your compliance.</p>
                        <p>Thank you,<br>Barangay Sto. Niño</p>
                    """
                    body_txt = (
                        f"Hi {owner_name},\n\n"
                        f"Your business closure payment has been confirmed for {bname} (ID: {business_id:06d}).\n"
                        f"Status: CLOSED\n\n"
                        f"All outstanding dues have been settled. Your business is now officially closed.\n\n"
                        f"Thank you for your compliance.\n\n"
                        f"Thank you,\nBarangay Sto. Niño\n"
                    )
                    send_email(
                        subject=subject,
                        to=[(owner_name, owner_email)],
                        body_text=body_txt,
                        body_html=body_html,
                        from_name="Barangay Sto. Niño",
                        fail_silently=True,
                    )
                except Exception:
                    pass
            
            # Send in-app notification
            if owner_person_id:
                try:
                    notify_user(
                        user_type_id=1,  # PERSON
                        person_id=owner_person_id,
                        staff_id=None,
                        title="Business Closure Confirmed",
                        body=f"All closure payments confirmed for '{bname}'. Business status: CLOSED.",
                        deep_link=f"/business/{business_id}"
                    )
                except Exception:
                    pass
        except Exception:
            pass
        
        messages.success(request, "All unpaid closure items were paid and the business was marked CLOSED.")
    except Exception as e:
        messages.error(request, f"Failed to process bulk closure payment: {e}")

    return redirect("treasurer:closure_group", business_id=business_id)


# ========= REFUND COMPLETE =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def treasurer_complete_refund(request: HttpRequest, doc_request_id: int):
    print("\n" + "="*72)
    print("[REFUND DEBUG] treasurer_complete_refund CALLED")
    print(f"[REFUND DEBUG] doc_request_id = {doc_request_id}")

    staff_id = _staff_id(request) or 0
    print(f"[REFUND DEBUG] staff_id       = {staff_id}")

    if staff_id <= 0:
        print("[REFUND DEBUG] ERROR: No staff in session")
        messages.error(request, "Staff session required.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    # capture raw POST (sanitized)
    try:
        safe_post = {
            "refund_id": request.POST.get("refund_id"),
            "provider_refund_id": request.POST.get("provider_refund_id"),
            "refund_receipt_no": request.POST.get("refund_receipt_no"),
        }
        print("[REFUND DEBUG] POST payload   =", safe_post)
    except Exception as e:
        print("[REFUND DEBUG] Could not pretty-print POST:", e)

    # the refund ticket to complete (e.g. from the page’s form)
    try:
        refund_id = int(request.POST.get("refund_id") or 0)
    except Exception:
        refund_id = 0
    provider_refund_id = (request.POST.get("provider_refund_id") or "").strip() or None
    refund_receipt_no  = (request.POST.get("refund_receipt_no")  or "").strip() or None

    print(f"[REFUND DEBUG] refund_id            = {refund_id}")
    print(f"[REFUND DEBUG] provider_refund_id   = {provider_refund_id!r}")
    print(f"[REFUND DEBUG] refund_receipt_no    = {refund_receipt_no!r}")

    if not refund_id:
        print("[REFUND DEBUG] ERROR: Missing refund_id")
        messages.error(request, "Missing refund ticket id.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    payload = {
        "p_payment_refund_id":  refund_id,
        "p_treasurer_staff_id": int(staff_id),
        "p_provider_refund_id": provider_refund_id,
        "p_refund_receipt_no":  refund_receipt_no,
    }
    print("[REFUND DEBUG] RPC payload      =", payload)

    try:
        res = supabase.rpc("treasurer_complete_refund", payload).execute()
        print("[REFUND DEBUG] RPC .data       =", getattr(res, "data", None))
        print("[REFUND DEBUG] RPC .error      =", getattr(res, "error", None))
        if getattr(res, "error", None):
            raise RuntimeError(res.error.message)
    except Exception as e:
        print("[REFUND DEBUG] EXCEPTION during RPC:", e)
        messages.error(request, f"Failed to complete refund: {escape(str(e))}")
        print("="*72 + "\n")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    print("[REFUND DEBUG] SUCCESS: refund completed and logged.")
    print("="*72 + "\n")
    messages.success(request, "Refund completed and logged.")
    return redirect("treasurer:detail", doc_request_id=doc_request_id)


# ========= REFUNDS LIST (payment_refund table) =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def payment_refunds(request: HttpRequest):
    """
    Shows rows from payment_refund with search + filters.
    """
    q = (request.GET.get("q") or "").strip() or None
    statuses = [s.strip().upper() for s in request.GET.getlist("status") if s.strip()]
    method_ids_raw = [m.strip() for m in request.GET.getlist("method_id") if m.strip()]

    # Page size
    per_page_options = [5, 10, 25, 50, 100]
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 10
    if per_page not in per_page_options:
        per_page = 10

    # Map payment_method_id -> name (and build choices)
    methods_all = list_payment_methods() or []
    method_options = []
    method_name_by_id = {}
    for m in methods_all:
        mid = m.get("payment_method_id")
        name = (m.get("method_name") or "").strip() or f"Method {mid}"
        if mid is not None:
            mid_int = int(mid)
            method_options.append({"id": mid_int, "label": name})
            method_name_by_id[mid_int] = name

    # Base query
    query = (supabase
             .table("payment_refund")
             .select("*")
             .order("created_at", desc=True))

    # Search
    if q:
        ors = [f"reason.ilike.%{q}%", f"refund_receipt_no.ilike.%{q}%", f"provider_refund_id.ilike.%{q}%"]
        if q.isdigit():
            ors.append(f"doc_request_id.eq.{q}")
            ors.append(f"payment_refund_id.eq.{q}")
        query = query.or_(",".join(ors))

    # Filters
    if statuses:
        query = query.in_("status", statuses)

    method_ids: list[int] = []
    for token in method_ids_raw:
        if token.isdigit():
            method_ids.append(int(token))
    if method_ids:
        query = query.in_("payment_method_id", method_ids)

    # Pull rows
    res = query.limit(1000).execute()
    rows = res.data or []

    # Massage rows for display
    def _to_f(x):
        try:
            return float(x)
        except Exception:
            return None

    for r in rows:
        r["refund_amount_f"] = _to_f(r.get("refund_amount"))
        r["created_fmt"] = _fmt_occured_at(r.get("created_at"))
        r["completed_fmt"] = _fmt_occured_at(r.get("completed_at"))
        r["approved_fmt"] = _fmt_occured_at(r.get("approved_at"))
        mid = r.get("payment_method_id")
        if isinstance(mid, str) and mid.isdigit():
            mid = int(mid)
        r["method_name"] = method_name_by_id.get(mid) if mid is not None else None

        status = (r.get("status") or "").upper() or "—"
        r["status_ui"] = STATUS_UI.get(status) or {
            "label": status.replace("_", " ").title(),
            "cls": "badge text-bg-secondary"
        }

        det = r.get("details") or {}
        if isinstance(det, str):
            try:
                det = json.loads(det) or {}
            except Exception:
                det = {}
        r["amount_due_f"] = _to_f(det.get("amount_due"))
        or_numbers = det.get("or_numbers") or []
        r["or_numbers_str"] = ", ".join([str(x) for x in or_numbers if x]) if isinstance(or_numbers, list) else None
        r["online_paid_f"] = _to_f(det.get("online_paid"))
        r["or_collected_f"] = _to_f(det.get("or_collected"))

    # Pagination
    paginator = Paginator(rows, per_page)
    try:
        page_num = int(request.GET.get("page", "1") or "1")
    except Exception:
        page_num = 1
    if page_num < 1:
        page_num = 1
    if paginator.num_pages >= 1 and page_num > paginator.num_pages:
        page_num = paginator.num_pages
    try:
        page_obj = paginator.page(page_num)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)

    status_choices = ["CREATED", "REQUESTED", "PENDING", "APPROVED", "COMPLETED", "DECLINED"]
    selected_methods = [opt for opt in method_options if opt["id"] in method_ids]
    active_count = (1 if q else 0) + (1 if statuses else 0) + (1 if method_ids else 0)

    user_role = _auth_role_name(request)
    ctx = {
        'page_path': f'{user_role} / Payment Refunds',
        'page_title': 'Payment Refunds',
        "q": q or "",
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "page_numbers": page_numbers,
        "is_paginated": paginator.num_pages > 1,

        "statuses": statuses,
        "status_choices": status_choices,

        "method_ids": method_ids,
        "method_options": method_options,
        "selected_methods": selected_methods,

        "per_page": per_page,
        "per_page_options": per_page_options,

        "active_count": active_count,
    }
    return render(request, "treasurer/payment_refunds.html", ctx)


def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None


@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
@nocache
@inject
def financial_report(
    request: HttpRequest,
    or_service: IORService = Provide[AppContainer.or_service],
) -> HttpResponseRedirect | HttpResponseRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = ORFilters(request.GET or None)

    search = request.GET.get("search") or request.GET.get("q")
    pay_meth = _to_int_or_none(request.GET.get("pay_meth"))
    month = _to_int_or_none(request.GET.get("month"))
    year = _to_int_or_none(request.GET.get("year"))
    date_from = request.GET.get("date_from") or None
    date_to = request.GET.get("date_to") or None
    
    # Check if this is an AJAX request for rows only
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    template_mode = request.GET.get("tpl")

    rows = or_service.execute(
        search=search,
        payment_method=pay_meth,
        month=month,
        year=year,
        date_from=date_from,
        date_to=date_to
    )

    # Calculate total
    total_amount = sum(float(r.amount_paid or 0) for r in rows)

    if (search or pay_meth is not None or month or year or date_from or date_to):
        form = ORFilters()

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Return only rows template for AJAX requests
    if is_ajax and template_mode == "rows":
        return render(
            request,
            "financial/_financial_report_rows.html",
            {"rows": page_obj.object_list, "total_amount": total_amount}
        )

    return render(
        request,
        "financial/financial_report.html",
        {
            'page_path': f'{user_role} / Financial Report',
            'page_title': 'Financial Report',
            'form': form,
            'page_obj': page_obj,
            'search_url': 'treasurer:financial_report_search',
            'total_amount': total_amount,
        },
    )


# 1) IMPORTS — extend your existing fees_service import block
from .services.fees_service import (
    search_fee_items, recent_fee_changes, update_fee_amount,
    add_fee, fetch_fee_full, list_document_types, upsert_fee,
    # NEW:
    list_fee_document_types,
    search_fee_items_by_doc_type_id,
)

# If you don't already have this helper here, reuse the split you imported from utils.helpers
def _split_main_sub(name: str) -> tuple[str, str | None]:
    name = (name or "").strip()
    main, sub = name, None
    for sep in [" – ", " — ", " - "]:
        if sep in name:
            parts = [p.strip() for p in name.split(sep, 1)]
            if len(parts) == 2:
                main, sub = parts[0], parts[1]
            break
    return main, sub


# 2) NEW: Level-1 index (table of Document Types with counts)
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def fees_index(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 10
    if per_page not in (5, 10, 25, 50):
        per_page = 10

    # Fetch and filter by q (server-side, like your fees view)
    types_all = list_fee_document_types() or []
    if q:
        q_up = q.upper()
        types_all = [t for t in types_all
                     if q_up in (t.get("request_document_type_name") or "").upper()]

    # Paginate
    paginator = Paginator(types_all, per_page)
    try:
        page = int(request.GET.get("page", "1") or "1")
    except Exception:
        page = 1
    if page < 1:
        page = 1
    if paginator.num_pages >= 1 and page > paginator.num_pages:
        page = paginator.num_pages
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)
    history = recent_fee_changes(limit=6)
    user_role = _auth_role_name(request)

    ctx = {
        'page_path' : f'{user_role} / Fee Catalog',
        'page_title' : 'Fee Catalog',
        "q": q or "",
        "per_page": per_page,
        "is_paginated": paginator.num_pages > 1,
        "paginator": paginator,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "history": history,
    }
    return render(request, "treasurer/fees_index.html", ctx)



# treasurer/views.py (or appropriate module)
from typing import Tuple
from django.shortcuts import render, redirect
from django.core.paginator import Paginator, EmptyPage
from django.contrib import messages
from django.views.decorators.http import require_GET

# service helpers (adjust import path to match your project structure)
from treasurer.services.fees_service import (
    list_fee_document_types,
    search_fee_items_by_doc_type_id,
    recent_fee_changes,
)


@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def fees_by_type(request, doc_type_id: int):
    """
    Level-2: Browse fees scoped to a single document type.

    Query params:
      - q: optional search text
      - per_page: 5|10|25|50 (default 5 in the original)
      - page: page number

    Context provided to template (treasurer/fees.html):
      - q, per_page, is_paginated, paginator, page_obj, page_numbers, history
      - selected_doc_type_id, selected_doc_type
      - doc_types, fee_types, doc_types_all, fee_types_all, active_count (left empty to hide multi-type chips)
    """
    q = (request.GET.get("q") or "").strip() or None

    # per-page parsing (default 5 to match your original snippet)
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 5
    if per_page not in (5, 10, 25, 50):
        per_page = 5

    # Resolve the selected doc type name for breadcrumb (from service)
    types = list_fee_document_types() or []
    selected_doc_type = None
    try:
        for t in types:
            # ensure robust comparison (rpc may return id as int or string)
            if int(t.get("request_document_type_id") or t.get("id") or 0) == int(doc_type_id):
                selected_doc_type = (
                    t.get("request_document_type_name")
                    or t.get("name")
                    or t.get("request_document_type")
                )
                break
    except Exception:
        selected_doc_type = None

    if not selected_doc_type:
        messages.error(request, "Unknown document type.")
        return redirect("treasurer:fees_index")

    # Fetch items for this doc type (RPC) and prepare name_main/name_sub
    items_all = search_fee_items_by_doc_type_id(doc_type_id, q) or []
    for r in items_all:
        # _split_main_sub returns (main, sub). Example implementation should live in treasurer.utils
        try:
            main, sub = _split_main_sub(r.get("name") or r.get("fee_name") or "")
        except Exception:
            main, sub = (r.get("name") or r.get("fee_name") or ""), ""
        r["name_main"] = main
        r["name_sub"] = sub
        if "is_active" not in r:
            r["is_active"] = True

    # Pagination
    paginator = Paginator(items_all, per_page)
    try:
        page = int(request.GET.get("page", "1") or "1")
    except Exception:
        page = 1
    if page < 1:
        page = 1
    if paginator.num_pages >= 1 and page > paginator.num_pages:
        page = paginator.num_pages
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)

    page_numbers = build_page_numbers(page_obj.number, paginator.num_pages)

    # Use recent_fee_changes for sidebar/history (you can later replace with per-fee timeline)
    history = recent_fee_changes(limit=6) or []
    user_role = _auth_role_name(request)

    ctx = {
        'page_path' : f'{user_role} / Fee Catalog',
        'page_title' : 'Fee Catalog',
        "q": q or "",
        "per_page": per_page,
        "is_paginated": paginator.num_pages > 1,
        "paginator": paginator,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "history": history,

        # Tell fees.html we’re scoped to a type
        "selected_doc_type_id": doc_type_id,
        "selected_doc_type": selected_doc_type,

        # Hide multi-type chips in fees.html since we're already scoped
        "doc_types": [],
        "fee_types": [],
        "doc_types_all": [],
        "fee_types_all": [],
        "active_count": 0,
    }
    return render(request, "treasurer/fees.html", ctx)


# ========= PEOPLE REQUEST HISTORY =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def people_requests(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    try:
        res = supabase.rpc("get_person_request_counts").execute()
        rows = res.data or []
    except Exception:
        rows = []
    if q:
        q_up = q.upper()
        rows = [r for r in rows if q_up in (r.get("person_name") or "").upper() or q in str(r.get("person_id") or "")]
    paginator = Paginator(rows, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    user_role = _auth_role_name(request)
    return render(request, "treasurer/people_requests.html", {
        'page_path': f'{user_role} / People Requests',
        'page_title': 'People Requests',
        "q": q or "",
        "page_obj": page_obj,
        "paginator": paginator,
    })


@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def person_request_history(request: HttpRequest, person_id: int):
    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or []
    doc_types_filter = request.GET.getlist("doc_type") or []
    try:
        res = supabase.rpc("get_document_request_history", {"p_person_id": person_id}).execute()
        requests = res.data or []
    except Exception:
        messages.error(request, "Failed to load request history.")
        return redirect("treasurer:people_requests")
    all_doc_types = sorted(set(dt for r in requests for dt in (r.get("doc_types") or [])))
    if statuses:
        requests = [r for r in requests if r.get("status") in statuses]
    if doc_types_filter:
        requests = [r for r in requests if any(dt in doc_types_filter for dt in (r.get("doc_types") or []))]
    if q:
        q_up = q.upper()
        requests = [r for r in requests if 
            q_up in (r.get("request_code") or "").upper() or
            q_up in (r.get("latest_or_number") or "").upper() or
            any(q_up in (dt or "").upper() for dt in (r.get("doc_types") or [])) or
            any(q_up in (p or "").upper() for p in (r.get("purposes") or []))]
    person = {"person_id": person_id, "full_name": requests[0].get("requested_by_name") if requests else "Unknown"}
    for r in requests:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {"label": r.get("status") or "—", "cls": "badge text-bg-secondary"}
        r["created_fmt"] = _fmt_occured_at(r.get("created_at"))
        r["amount_due_f"] = float(r.get("amount_due") or 0)
        r["total_paid_f"] = float(r.get("total_paid") or 0)
        r["balance_f"] = float(r.get("balance") or 0)
        r["doc_types_display"] = ", ".join(r.get("doc_types") or [])
        r["purposes_display"] = ", ".join(r.get("purposes") or [])
    paginator = Paginator(requests, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    user_role = _auth_role_name(request)
    return render(request, "treasurer/person_request_history.html", {
        'page_path': f'{user_role} / Person History',
        'page_title': 'Person History',
        "person": person,
        "requests": page_obj.object_list,
        "statuses": statuses,
        "doc_types": all_doc_types,
        "doc_types_filter": doc_types_filter,
        "q": q or "",
        "page_obj": page_obj,
        "paginator": paginator,
    })
