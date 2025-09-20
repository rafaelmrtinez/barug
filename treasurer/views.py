from __future__ import annotations
from typing import Any, Dict, List
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import escape

from authentication.supabase_client import supabase

STATUS_UI = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}

ACTION_LABELS = {
    "REQUEST_CREATED":  "Request Created",
    "STATUS_CHANGED":   "Status Changed",
    "PAYMENT_ACCEPTED": "Payment Accepted",
    "LINE_ADDED":       "Item Added",
    "DECLINED":         "Declined",
}

def _staff_id(request: HttpRequest) -> int | None:
    prof = getattr(request, "profile", None)
    return getattr(prof, "staff_id", None) or request.session.get("staff_id")

def _has_role(request: HttpRequest, want: str) -> bool:
    prof = getattr(request, "profile", None)
    roles = set()
    if prof and getattr(prof, "roles", None):
        roles.update({r.upper() for r in prof.roles})
    if getattr(prof, "role", None):
        roles.add(str(prof.role).upper())
    if request.session.get("role_name"):
        roles.add("TREASURER")
    return want.upper() in roles or ("TREASURER" in roles if want.upper() == "TREASURER" else False)

def _titleize(s: str | None) -> str:
    return "" if not s else s.replace("_", " ").title()

def _guard(request: HttpRequest) -> HttpResponse | None:
    if not _has_role(request, "TREASURER"):
        return HttpResponseForbidden("Treasurer access required.")
    if not _staff_id(request):
        return HttpResponseForbidden("Missing staff id.")
    return None


# ========= Queue =========
def queue(request: HttpRequest):
    # if (g := _guard(request)): return g

    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or ["FOR_TREASURER_REVIEW", "PAID", "FOR_PRINTING"]

    query = supabase.table("v_doc_request_list_ex").select("*").order("doc_request_id", desc=True)
    if statuses:
        query = query.in_("status", statuses)
    if q:
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.cs.{{{q}}},purposes.cs.{{{q}}}")

    res = query.limit(50).execute()
    rows: List[Dict[str, Any]] = res.data or []

    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {"label": r.get("status"), "cls": "badge text-bg-secondary"}
        r["purposes_display"] = [_titleize(p) for p in (r.get("purposes") or [])]

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
def detail(request: HttpRequest, doc_request_id: int):
    # if (g := _guard(request)): return g

    bundle = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(bundle, "error", None):
        messages.error(request, f"Supabase error: {escape(bundle.error.message)}")
        return redirect("treasurer:queue")

    data: Dict[str, Any] = bundle.data or {}
    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline: List[Dict[str, Any]] = data.get("timeline", []) or []

    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}

    # lines presentation
    for l in lines:
        l["purpose_display"] = _titleize(l.get("purpose_code"))
        details = l.get("details") or {}
        l["reason_chips"] = list(l.get("reasons_applied") or details.get("reason_tags") or [])
        l["is_exempt"] = bool(l.get("is_exempt") or False)

    # Timeline presentation
    for e in timeline:
        e["action_display"] = ACTION_LABELS.get(e.get("action")) or _titleize(e.get("action"))
        to_status = e.get("to_status")
        if not to_status:
            det = e.get("details") or {}
            if isinstance(det, dict):
                to_status = det.get("to_status")
        if to_status:
            e["to_status_display"] = (STATUS_UI.get(to_status) or {"label": _titleize(to_status)}).get("label")

    # Payment methods + find WAIVED id
    pm_res = supabase.rpc("get_payment_methods", {}).execute()
    methods = pm_res.data or []
    waived_method_id = None
    for m in methods:
        if (m.get("method_name") or "").strip().upper() == "WAIVED":
            waived_method_id = m.get("payment_method_id")
            break

    # Auth letter links
    BUCKET = "authorization-letters"
    supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
    public_prefix = f"{supabase_url}/storage/v1/object/public/{BUCKET}/" if supabase_url else ""
    seen, paths = set(), []
    for p in (header.get("auth_letter_paths") or []):
        if p and p not in seen: seen.add(p); paths.append(p)
    for ln in lines:
        p = (ln.get("details") or {}).get("auth_letter_path")
        if p and p not in seen: seen.add(p); paths.append(p)
    auth_links = []
    for p in paths:
        name = str(p).split("/")[-1]
        url = (public_prefix + str(p).lstrip("/")) if public_prefix else ""
        auth_links.append({"name": name, "url": url, "is_pdf": name.lower().endswith(".pdf")})

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
def take_payment(request: HttpRequest, doc_request_id: int):
    staff_id = _staff_id(request) or 2
    method_id = int(request.POST.get("payment_method_id", "0") or 0)
    amount_paid = Decimal(request.POST.get("amount_paid", "0") or "0")

    # allow zero for WAIVED; block only negatives / missing method
    if amount_paid < 0 or method_id <= 0:
        messages.error(request, "Enter a valid amount and payment method.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    # 1) Accept payment (or waived 0.00)
    res = supabase.rpc("treasurer_accept_payment", {
        "p_amount_paid": float(amount_paid),
        "p_doc_request_id": doc_request_id,
        "p_payment_method_id": method_id,
        "p_received_by_staff_id": staff_id,
        # "p_or_number": "OR-..."
    }).execute()

    if getattr(res, "error", None):
        messages.error(request, f"Payment failed: {escape(res.error.message)}")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

    or_id = res.data  # int

    # 2) Fetch OR details for toast
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
    mark_res = supabase.rpc("mark_request_for_printing", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": "Auto-marked after payment"
    }).execute()

    if getattr(mark_res, "error", None):
        messages.warning(request, f"Payment ok, but failed to mark FOR_PRINTING: {escape(mark_res.error.message)}")
    else:
        messages.info(request, "Request moved to FOR_PRINTING.")

    return redirect("treasurer:detail", doc_request_id=doc_request_id)


# ========= Fees search + update =========
def fees(request: HttpRequest):
    # if (g := _guard(request)): return g

    q = (request.GET.get("q") or "").strip() or None
    fee_res = supabase.rpc("search_fee_items", {"p_query": q}).execute()
    items = fee_res.data or []

    hist_res = supabase.rpc("get_recent_fee_changes", {"p_limit": 50}).execute()
    history = hist_res.data or []

    return render(request, "treasurer/fees.html", {"q": q or "", "items": items, "history": history})


def fee_update(request: HttpRequest):
    if request.method != "POST":
        return redirect("treasurer:fees")
    # if (g := _guard(request)): return g

    staff_id = _staff_id(request) or 2
    fee_code = (request.POST.get("fee_code") or "").strip()
    reason = (request.POST.get("reason") or "").strip() or None
    try:
        new_amount = float(Decimal(request.POST.get("new_amount", "0")))
    except Exception:
        messages.error(request, "Invalid amount.")
        return redirect("treasurer:fees")

    if not fee_code or new_amount < 0:
        messages.error(request, "Provide a valid fee code and amount.")
        return redirect("treasurer:fees")

    res = supabase.rpc("treasurer_update_fee_amount", {
        "p_changed_by_staff_id": staff_id,
        "p_fee_code": fee_code,
        "p_new_amount": new_amount,
        "p_reason": reason,
    }).execute()

    if getattr(res, "error", None):
        messages.error(request, f"Update failed: {escape(res.error.message)}")
    else:
        messages.success(request, f"{fee_code} updated to ₱{new_amount:,.2f}.")
    return redirect("treasurer:fees")


# ========= Add/Upsert Fee =========
def fee_add(request: HttpRequest):
    dt_res = supabase.rpc("get_document_types", {}).execute()
    doc_types: List[Dict[str, Any]] = dt_res.data or []

    units = ["per_doc", "per_copy", "per_event", "per_month", "per_year", "per_hour", "per_unit_per_day", "per_use"]

    if request.method != "POST":
        return render(request, "treasurer/fee_add.html", {"doc_types": doc_types, "units": units})

    staff_id = _staff_id(request) or 2

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

    if not doc_type_name:
        messages.error(request, "Pick a Document Type or enter a new one.")
        return redirect("treasurer:fee_add")
    if not fee_code:
        messages.error(request, "Fee Code is required.")
        return redirect("treasurer:fee_add")
    if not fee_name:
        messages.error(request, "Fee Name is required.")
        return redirect("treasurer:fee_add")
    if current_amount is None or current_amount < 0:
        messages.error(request, "Enter a valid Current Amount.")
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

    res = supabase.rpc("treasurer_add_fee", payload).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Add fee failed: {escape(res.error.message)}")
        return redirect("treasurer:fee_add")

    messages.success(request, f"Saved: {fee_code} – {fee_name} (Type: {doc_type_name}, Amount ₱{current_amount:,.2f}).")
    return redirect(f"{settings.FORCE_SCRIPT_NAME or ''}/treasurer/fees/?q={fee_code}")


# ========= Edit/Upsert Fee =========
def fee_edit(request: HttpRequest, fee_code: str):
    snap = supabase.rpc("fetch_fee_full", {"p_fee_code": fee_code}).execute()
    if getattr(snap, "error", None):
        messages.error(request, f"Load failed: {escape(snap.error.message)}")
        return redirect("treasurer:fees")

    data = snap.data or {}
    fee = (data.get("fee") or {})
    purposes = data.get("purposes") or []
    surcharges = data.get("surcharges") or []

    dtypes = supabase.rpc("get_document_types", {}).execute()
    doc_types = dtypes.data or []

    if request.method != "POST":
        return render(request, "treasurer/fee_edit.html", {
            "fee_code": fee_code,
            "fee": fee,
            "purposes": purposes,
            "surcharges": surcharges,
            "doc_types": doc_types,
        })

    staff_id = _staff_id(request) or 2

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

    res = supabase.rpc("treasurer_upsert_fee", payload).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Update failed: {escape(res.error.message)}")
        return redirect("treasurer:fee_edit", fee_code=fee_code)

    messages.success(request, f"{fee_code} saved.")
    return redirect("treasurer:fee_edit", fee_code=fee_code)
