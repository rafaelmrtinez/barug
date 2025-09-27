from __future__ import annotations

from typing import Any, Dict, List
from decimal import Decimal
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.views.decorators.http import require_GET, require_POST

from authentication.guards import session_login_required, role_required
from authentication.supabase_client import supabase  # still used for the small OR fetch

from .services.requests_service import list_requests, list_business_requests, fetch_detail_bundle, build_auth_links
from .services.payments_service import list_payment_methods, accept_payment, mark_for_printing
from .services.fees_service import (
    search_fee_items, recent_fee_changes, update_fee_amount,
    add_fee, fetch_fee_full, list_document_types, upsert_fee
)
from .utils.ui import STATUS_UI, ACTION_LABELS, titleize

TREASURER_ROLE = "Barangay Treasurer"
#1 
def _staff_id(request: HttpRequest) -> int | None:
    # Prefer session-based id set at login; fallback to attached profile(s)
    auth = request.session.get("auth") or {}
    sid = auth.get("staff_id")
    if sid:
        return sid
    prof = getattr(request, "profile", None) or getattr(request, "person_profile", None)
    return getattr(prof, "staff_id", None)

# ========= Queue =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def queue(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or ["FOR_TREASURER_REVIEW", "PAID", "FOR_PRINTING"]

    rows = list_requests(q, statuses, limit=50)
    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {"label": r.get("status") or "—", "cls": "badge text-bg-secondary"}
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

# ========= Detail (with payment panel) =========
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

    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}

    # lines presentation
    for l in lines:
        l["purpose_display"] = titleize(l.get("purpose_code"))
        details = l.get("details") or {}
        l["reason_chips"] = list(l.get("reasons_applied") or details.get("reason_tags") or [])
        l["is_exempt"] = bool(l.get("is_exempt") or False)

    # Timeline presentation
    for e in timeline:
        e["action_display"] = ACTION_LABELS.get(e.get("action")) or titleize(e.get("action"))
        to_status = e.get("to_status") or (e.get("details") or {}).get("to_status")
        if to_status:
            e["to_status_display"] = (STATUS_UI.get(to_status) or {"label": titleize(to_status)}).get("label")

    # Payment methods + find WAIVED id
    methods = list_payment_methods()
    waived_method_id = next(
        (m.get("payment_method_id") for m in methods if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # Auth letter links
    auth_links = build_auth_links(settings, header, lines)

    return render(request, "treasurer/detail.html", {
        "header": header,
        "status_ui": ui,
        "lines": lines,
        "payments": payments,
        "timeline": timeline,
        "methods": methods,
        "waived_method_id": waived_method_id,
        "auth_links": auth_links,
    })

# ========= Take payment (POST) =========
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

    # 2) Fetch OR details for toast (kept inline for brevity)
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

    # 3) Move to FOR_PRINTING right away
    try:
        mark_for_printing(doc_request_id=doc_request_id, staff_id=staff_id, reason="Auto-marked after payment")
        messages.info(request, "Request moved to FOR_PRINTING.")
    except Exception as e:
        messages.warning(request, f"Payment ok, but failed to mark FOR_PRINTING: {escape(str(getattr(e, 'message', e)))}")

    return redirect("treasurer:detail", doc_request_id=doc_request_id)

# ========= Fees search + update =========
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def fees(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None
    items = search_fee_items(q)
    history = recent_fee_changes(limit=50)
    return render(request, "treasurer/fees.html", {"q": q or "", "items": items, "history": history})

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

# ========= Add/Upsert Fee =========
@session_login_required
@role_required(TREASURER_ROLE)
def fee_add(request: HttpRequest):
    doc_types = list_document_types()
    units = ["per_doc", "per_copy", "per_event", "per_month", "per_year", "per_hour", "per_unit_per_day", "per_use"]

    if request.method != "POST":
        return render(request, "treasurer/fee_add.html", {"doc_types": doc_types, "units": units})

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_add")

    use_new = (request.POST.get("use_new_doc") == "1")
    doc_type_name = (request.POST.get("doc_type_name_new") or "").strip() if use_new \
                    else (request.POST.get("doc_type_name") or "").strip()

    fee_code  = (request.POST.get("fee_code") or "").strip()
    fee_name  = (request.POST.get("fee_name") or "").strip()
    unit      = (request.POST.get("unit") or "per_doc").strip()

    from decimal import Decimal as _D
    try:
        current_amount = float(_D(request.POST.get("current_amount") or "0"))
    except Exception:
        current_amount = -1
    try:
        max_amount_raw = request.POST.get("max_amount", "").strip()
        max_amount = float(_D(max_amount_raw)) if max_amount_raw != "" else None
    except Exception:
        max_amount = None

    ex_ftj      = bool(request.POST.get("ex_ftj"))
    ex_senior   = bool(request.POST.get("ex_senior"))
    ex_pwd      = bool(request.POST.get("ex_pwd"))
    ex_indigent = bool(request.POST.get("ex_indigent"))
    ex_student  = bool(request.POST.get("ex_student"))
    is_active   = bool(request.POST.get("is_active")) if request.POST.get("is_active") is not None else True

    purpose_code   = (request.POST.get("purpose_code") or "").strip() or None
    purpose_label  = (request.POST.get("purpose_label") or "").strip() or None
    default_offense_no = request.POST.get("default_offense_no", "").strip()
    default_offense_no = int(default_offense_no) if default_offense_no.isdigit() else None

    import json as _json
    try:
        default_details = _json.loads(request.POST.get("default_details") or "{}")
        if not isinstance(default_details, dict):
            default_details = {}
    except Exception:
        default_details = {}

    s1 = (request.POST.get("s1") or "").strip()
    s2 = (request.POST.get("s2") or "").strip()
    s3 = (request.POST.get("s3") or "").strip()
    surcharges = []
    from decimal import Decimal as _Dec
    if s1:
        try: surcharges.append({"offense_no": 1, "percent": float(_Dec(s1))})
        except Exception: pass
    if s2:
        try: surcharges.append({"offense_no": 2, "percent": float(_Dec(s2))})
        except Exception: pass
    if s3:
        try: surcharges.append({"offense_no": 3, "percent": float(_Dec(s3))})
        except Exception: pass
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
        "p_changed_by_staff_id": staff_id,
        "p_reason": reason,
    }

    try:
        add_fee(payload)
    except Exception as e:
        messages.error(request, f"Add fee failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_add")

    messages.success(request, f"Saved: {fee_code} – {fee_name} (Type: {doc_type_name}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")

# ========= Edit/Upsert Fee =========
@session_login_required
@role_required(TREASURER_ROLE)
def fee_edit(request: HttpRequest, fee_code: str):
    try:
        data = fetch_fee_full(fee_code)
    except Exception as e:
        messages.error(request, f"Load failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fees")

    fee = (data.get("fee") or {})
    purposes = data.get("purposes") or []
    surcharges = data.get("surcharges") or []
    doc_types = list_document_types()

    if request.method != "POST":
        return render(request, "treasurer/fee_edit.html", {
            "fee_code": fee_code,
            "fee": fee,
            "purposes": purposes,
            "surcharges": surcharges,
            "doc_types": doc_types,
        })

    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session is required.")
        return redirect("treasurer:fee_edit", fee_code=fee_code)

    payload: Dict[str, Any] = {
        "p_fee_code": fee_code,
        "p_changed_by_staff_id": staff_id,
        "p_new_name": (request.POST.get("fee_name") or "").strip() or None,
        "p_new_unit": (request.POST.get("unit") or "").strip() or None,
        "p_new_current_amount": float(Decimal(request.POST.get("current_amount") or "0")) if request.POST.get("current_amount") else None,
        "p_new_max_amount": float(Decimal(request.POST.get("max_amount") or "0")) if request.POST.get("max_amount") else None,
        "p_exempt_ftj": True if request.POST.get("ex_ftj") else None,
        "p_exempt_senior": True if request.POST.get("ex_senior") else None,
        "p_exempt_pwd": True if request.POST.get("ex_pwd") else None,
        "p_exempt_indigent": True if request.POST.get("ex_indigent") else None,
        "p_exempt_student": True if request.POST.get("ex_student") else None,
        "p_is_active": True if request.POST.get("is_active") else None,
        "p_doc_type_name": (request.POST.get("doc_type_name") or "").strip() or None,
        "p_reason": (request.POST.get("reason") or "").strip() or None,
    }

    import json
    purp_rows = []
    idx = 0
    while True:
        idx += 1
        pc = (request.POST.get(f"purp_{idx}_code") or "").strip()
        lbl = (request.POST.get(f"purp_{idx}_label") or "").strip()
        dt_override = (request.POST.get(f"purp_{idx}_dtype") or "").strip()
        det = (request.POST.get(f"purp_{idx}_details") or "").strip()
        off = (request.POST.get(f"purp_{idx}_offense") or "").strip()
        if not pc and not lbl and not det and not off and not dt_override:
            if idx > 50: break
            continue
        try:
            details = json.loads(det) if det else {}
            if not isinstance(details, dict): details = {}
        except Exception:
            details = {}
        purp_rows.append({
            "request_document_type_name": dt_override or None,
            "purpose_code": pc or None,
            "purpose_label": lbl or None,
            "default_details": details,
            "default_offense_no": int(off) if off.isdigit() else None
        })
    if purp_rows:
        payload["p_purposes"] = purp_rows

    sr = []
    for k in ("1","2","3"):
        val = (request.POST.get(f"surcharge_{k}") or "").strip()
        if val:
            try:
                sr.append({"offense_no": int(k), "percent": float(Decimal(val))})
            except Exception:
                pass
    if sr: payload["p_surcharges"] = sr

    try:
        upsert_fee(payload)
    except Exception as e:
        messages.error(request, f"Update failed: {escape(str(getattr(e, 'message', e)))}")
        return redirect("treasurer:fee_edit", fee_code=fee_code)

    messages.success(request, f"{fee_code} saved.")
    return redirect("treasurer:fee_edit", fee_code=fee_code)

# ---------- Business-only queue ----------
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
            # ensure both ids exist in each row
            # expects your v_doc_request_list_ex_v2 (or updated view) to expose business_id
            rows.append(r)

    return render(request, "treasurer/business_queue.html", {
        "rows": rows,
        "q": q or "",
        "statuses": statuses,
    })


# ---------- Business detail (with payment panel) ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_GET
def business_detail(request: HttpRequest, business_id: int, doc_request_id: int):
    # 1) Business profile
    biz_res = supabase.rpc("get_business_details", {"p_business_id": business_id}).execute()
    biz = (biz_res.data[0] if (biz_res and getattr(biz_res, "data", None)) else {}) or {}
    # normalize flag key
    biz["has_business_clearance"] = bool(
        biz.get("has_business_clearance") or biz.get("has_brgy_clearance")
    )

    # 2) Doc request bundle (for amount due, payments, etc.)
    header: Dict[str, Any] = {}
    payments: Dict[str, Any] = {}
    lines: List[Dict[str, Any]] = []
    try:
        bundle = fetch_detail_bundle(doc_request_id)
        header   = bundle.get("header")   or {}
        payments = bundle.get("payments") or {}
        lines    = bundle.get("lines")    or []
    except Exception as e:
        messages.warning(request, f"Could not load request details: {escape(str(getattr(e,'message',e)))}")

    # 3) Payment methods + find WAIVED id
    methods = list_payment_methods()
    waived_method_id = next(
        (m.get("payment_method_id") for m in methods if (m.get("method_name") or "").strip().upper() == "WAIVED"),
        None
    )

    # 4) Release history + year status (optional, keeps your previous UI)
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
        "status_ui": STATUS_UI.get(header.get("status") or "") or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"},
    })

# ---------- One-click: Pay -> set flag -> mark for printing ----------
@session_login_required
@role_required(TREASURER_ROLE)
@require_POST
def business_pay_and_print(request: HttpRequest, business_id: int, doc_request_id: int):
    staff_id = _staff_id(request) or 0
    if staff_id <= 0:
        messages.error(request, "Staff session required.")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    # pull posted form fields
    try:
        method_id = int(request.POST.get("payment_method_id", "0") or 0)
        amount_paid = float(Decimal(request.POST.get("amount_paid", "0") or "0"))
    except Exception:
        messages.error(request, "Invalid payment fields.")
        return redirect("treasurer:business_detail", business_id=business_id, doc_request_id=doc_request_id)

    # STEP 1: Accept payment (fail fast)
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

    # show OR info if we can
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

    # STEP 2: Set has_business_clearance = TRUE
    try:
        supabase.rpc("set_business_has_clearance_true", {"p_business_id": business_id}).execute()
        messages.info(request, "Business flag set: has_business_clearance = TRUE.")
    except Exception as e:
        messages.warning(request, f"Payment ok, but failed to set business flag: {escape(str(getattr(e,'message',e)))}")

    # STEP 3: Move to FOR_PRINTING
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
