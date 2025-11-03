from __future__ import annotations

from typing import Any, Dict, List
from decimal import Decimal
from datetime import datetime, date
import json
import re

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

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase

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
from .utils.ui import STATUS_UI, ACTION_LABELS, titleize

# >>> NEW: import extracted helpers (behavior unchanged)
from .utils.helpers import (
    _staff_id,
    _fmt_occured_at,
    _resolve_actor_name,
    _extract_payment_method_label,
    build_page_numbers,
    split_name_main_sub,
)

TREASURER_ROLE = "Barangay Treasurer"
PH_TZ = ZoneInfo("Asia/Manila")


# ========= DASHBOARD =========
# views.py (imports)
from treasurer.services.dashboard_api import build_dashboard_payload, PH_TZ

@session_login_required
@role_required(TREASURER_ROLE)
@nocache
def dashboard(request: HttpRequest):
    auth = request.session.get("auth")
    # initial snapshot -> template json_script
    dash = build_dashboard_payload("7d", None)
    return render(request, "treasurer/dashboard.html", {
        "page_path": "Barangay Treasurer/Dashboard",
        "page_title": "Dashboard",
        "auth": auth,
        "today": timezone.now().astimezone(PH_TZ).strftime("%b %d, %Y"),
        "dashboard_json": dash,
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

    rows = list_requests(q, statuses, limit=50)
    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {
            "label": r.get("status") or "—",
            "cls": "badge text-bg-secondary"
        }
        r["purposes_display"] = [titleize(p) for p in (r.get("purposes") or [])]

    status_options = [
        {"code": code, "label": meta["label"], "cls": meta["cls"], "checked": code in statuses}
        for code, meta in STATUS_UI.items()
    ]

    return render(request, "treasurer/queue.html", {
        "rows": rows,
        "q": q or "",
        "statuses": statuses,
        "status_options": status_options,
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

    context = {
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

    ctx = {
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
        return render(
            request,
            "treasurer/fee_purpose.html",
            {
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
        return render(request, "treasurer/fee_add.html", {
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
                    "event_display": raw_event.replace("_", " "),  # <- Option A: preformatted for template
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

        return render(request, "treasurer/fee_edit.html", {
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
            rows.append(r)

    return render(request, "treasurer/business_queue.html", {
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

    clr_res = supabase.rpc("list_business_clearances", {"p_business_id": business_id}).execute()
    clearances = (clr_res.data or []) if clr_res else []
    year = datetime.utcnow().year
    yr_res = supabase.rpc("check_business_clearance_for_year",
                          {"p_business_id": business_id, "p_year": year}).execute()
    year_status = (yr_res.data[0] if (yr_res and yr_res.data) else None)
    if year_status and "last_changed_at" not in year_status:
        year_status["last_changed_at"] = year_status.get("last_created_at")
    last_cleared_year = clearances[0]["year"] if clearances else None

    return render(request, "treasurer/business_details.html", {
        "biz": biz,
        "doc_request_id": doc_request_id,
        "header": header,
        "payments": payments,
        "methods": methods,
        "waived_method_id": waived_method_id,
        "clearances": clearances,
        "year_status": year_status,
        "last_cleared_year": last_cleared_year,
        "document_type_name": document_type_name,
        "status_ui": STATUS_UI.get(header.get("status") or "") or {
            "label": header.get("status") or "—",
            "cls": "badge text-bg-secondary"
        },
        "ctc_mode": ctc_mode,
        "ctc_ref_request_id": ctc_ref_request_id,
        "ctc_ref_header": ctc_ref_header,
        "ctc_ref_lines": ctc_ref_lines,
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

    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
        amount_paid = float(Decimal(request.POST.get("amount_paid", "0") or "0"))
    except Exception:
        messages.error(request, "Invalid payment fields.")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    or_id = None
    try:
        or_id = accept_payment(
            doc_request_id=doc_request_id,
            method_id=method_id,
            amount_paid=amount_paid,
            staff_id=staff_id,
        )
    except Exception as e:
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
        supabase.rpc("set_business_has_clearance_true", {"p_business_id": business_id}).execute()
        messages.info(request, "Business flag set: has_business_clearance = TRUE.")
    except Exception as e:
        messages.warning(request, f"Payment ok, but failed to set business flag: {escape(str(getattr(e,'message',e)))}")

    try:
        mark_for_printing(
            doc_request_id=doc_request_id,
            staff_id=staff_id,
            reason="Auto: after payment from Business Details"
        )
        messages.info(request, "Request moved to FOR_PRINTING.")
    except Exception as e:
        messages.warning(request, f"Payment ok, but failed to move to FOR_PRINTING: {escape(str(getattr(e,'message',e)))}")

    return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)


# ---------- BUSINESS RENEWAL LIST ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_renewal(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    period_types = [p.strip().upper() for p in request.GET.getlist("period_type") if p.strip()]
    year = request.GET.get("year", "").strip()
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

    if paid_filters:
        want_paid = "paid" in paid_filters and "unpaid" not in paid_filters
        want_unpaid = "unpaid" in paid_filters and "paid" not in paid_filters
        if want_paid:
            rows = [r for r in rows if r.get("paid_on")]
        elif want_unpaid:
            rows = [r for r in rows if not r.get("paid_on")]

    STATUS_ID_MAP = {8: "FOR_TREASURER_REVIEW", 9: "PAID"}
    for r in rows:
        name = "PAID" if r.get("paid_on") else STATUS_ID_MAP.get(r.get("request_status_id"), "—")
        ui = STATUS_UI.get(name) or {"label": name, "cls": "badge text-bg-secondary"}
        r["status_name"] = name
        r["status_ui"] = ui

        ptype = (r.get("period_type") or "").upper()
        yr = r.get("period_year")
        qtr = r.get("period_quarter")
        if ptype == "QUARTERLY":
            r["period_label"] = f"Q{qtr} {yr}" if (yr and qtr) else (ptype or "—")
        else:
            r["period_label"] = str(yr or "—")

        def _to_float(v):
            try:
                return float(v)
            except Exception:
                return None
        r["base_fee_quote_f"] = _to_float(r.get("base_fee_quote"))
        r["surcharge_quote_f"] = _to_float(r.get("surcharge_quote"))
        r["total_quote_f"] = _to_float(r.get("total_quote"))

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
    period_type_all = sorted({(r.get("period_type") or "").upper() for r in rows if r.get("period_type")})
    year_all = sorted({int(r.get("period_year")) for r in rows if r.get("period_year")}, reverse=True)

    ctx = {
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

    context = {
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
    """Accept a payment for a renewal request and call the renewal RPC.

    This mirrors the behavior of `take_payment` for regular requests but
    invokes the `treasurer_accept_renewal_payment` RPC via the service layer.
    """
    staff_id = _staff_id(request) or 0
    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
    except Exception:
        method_id = 0
    try:
        amount_paid = float(request.POST.get("amount_paid", "0") or 0)
    except Exception:
        amount_paid = 0.0

    or_number = (request.POST.get("or_number") or None)
    paid_on = (request.POST.get("paid_on") or None)

    if staff_id <= 0 or amount_paid < 0 or method_id <= 0:
        messages.error(request, "Enter a valid amount, method, and ensure your staff session is active.")
        return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)

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

    # Provide a success toast; details are already written by the RPC
    messages.success(request, f"Payment posted (clearance id {clearance_id}).")

    # Optionally attempt to mark printing or any other post-payment actions if needed
    return redirect("treasurer:business_renewal_detail", renewal_request_id=renewal_request_id)


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

    ctx = {
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


from treasurer.services.finreport_service import build_financial_report_payload

@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
@nocache
def financial_report(request):
    q = (request.GET.get("q") or "").strip() or None
    doc_type = (request.GET.get("doc_type") or "").strip() or None
    pm_raw = (request.GET.get("payment_method_id") or "").strip()
    payment_method_id = int(pm_raw) if pm_raw.isdigit() else None
    start_date = (request.GET.get("start_date") or "").strip() or None
    end_date = (request.GET.get("end_date") or "").strip() or None

    payload = build_financial_report_payload(start_date, end_date, q, doc_type, payment_method_id)

    # Paginate rows
    try:
        per_page = int(request.GET.get("per_page") or "25")
    except Exception:
        per_page = 25
    per_page = per_page if per_page in (10, 25, 50, 100) else 25

    paginator = Paginator(payload["rows"], per_page)
    try:
        page = int(request.GET.get("page") or "1")
    except Exception:
        page = 1

    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(1)

    return render(
        request,
        "treasurer/financial_report.html",
        {
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "per_page": per_page,
            "q": q or "",
            "doc_type": doc_type or "",
            "payment_method_id": payment_method_id or "",
            "start_date": start_date or "",
            "end_date": end_date or "",
            "filters": payload["filters"],
            "totals": payload["totals"],
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

    ctx = {
        "q": q or "",
        "per_page": per_page,
        "is_paginated": paginator.num_pages > 1,
        "paginator": paginator,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "history": history,
    }
    return render(request, "treasurer/fees_index.html", ctx)


# 3) NEW: Level-2 (reuse fees.html; scoped to a single document type id)
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def fees_by_type(request: HttpRequest, doc_type_id: int):
    q = (request.GET.get("q") or "").strip() or None
    try:
        per_page = int(request.GET.get("per_page", "10") or "10")
    except Exception:
        per_page = 5
    if per_page not in (5, 10, 25, 50):
        per_page = 5

    # Resolve the selected doc type name for breadcrumb
    types = list_fee_document_types() or []
    selected_doc_type = None
    for t in types:
        if int(t.get("request_document_type_id")) == int(doc_type_id):
            selected_doc_type = t.get("request_document_type_name")
            break
    if not selected_doc_type:
        messages.error(request, "Unknown document type.")
        return redirect("treasurer:fees_index")

    items_all = search_fee_items_by_doc_type_id(doc_type_id, q) or []
    for r in items_all:
        main, sub = _split_main_sub(r.get("name") or "")
        r["name_main"] = main
        r["name_sub"] = sub

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
    history = recent_fee_changes(limit=6)

    ctx = {
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
