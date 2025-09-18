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
        role = "TREASURER"
        roles.add(role)
    return want.upper() in roles or ("TREASURER" in roles if want.upper() == "TREASURER" else False)

def _titleize(s: str | None) -> str:
    return "" if not s else s.replace("_", " ").title()

def _guard(request: HttpRequest) -> HttpResponse | None:
    if not _has_role(request, "TREASURER"):
        return HttpResponseForbidden("Treasurer access required.")
    if not _staff_id(request):
        return HttpResponseForbidden("Missing staff id.")
    return None


# ========== Queue ==========
def queue(request: HttpRequest):
    # if (g := _guard(request)): return g

    q = (request.GET.get("q") or "").strip() or None
    statuses = request.GET.getlist("status") or ["FOR_TREASURER_REVIEW", "PAID"]

    query = supabase.table("v_doc_request_list_ex").select("*").order("doc_request_id", desc=True)
    if statuses:
        query = query.in_("status", statuses)
    if q:
        # search by code/type/purpose
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.cs.{{{q}}},purposes.cs.{{{q}}}")

    res = query.limit(50).execute()
    rows: List[Dict[str, Any]] = res.data or []

    for r in rows:
        r["status_ui"] = STATUS_UI.get(r.get("status")) or {"label": r.get("status"), "cls": "badge text-bg-secondary"}
        r["purposes_display"] = [_titleize(p) for p in (r.get("purposes") or [])]

    # Build options for the filter UI (no Python-in-template hacks)
    status_options = [
        {
            "code": code,
            "label": meta["label"],
            "cls": meta["cls"],
            "checked": code in statuses,
        }
        for code, meta in STATUS_UI.items()
    ]

    return render(
        request,
        "treasurer/queue.html",
        {
            "rows": rows,
            "q": q or "",
            "statuses": statuses,
            "status_options": status_options,
        },
    )


# ========== Detail (with payment panel) ==========
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
    timeline = data.get("timeline", []) or []

    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}
    for l in lines:
        l["purpose_display"] = _titleize(l.get("purpose_code"))

    # Payment methods
    pm_res = supabase.rpc("get_payment_methods", {}).execute()
    methods = pm_res.data or []

    # --- Build public URLs for authorization letters ---
    BUCKET = "authorization-letters"
    supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
    public_prefix = f"{supabase_url}/storage/v1/object/public/{BUCKET}/" if supabase_url else ""
    # Gather paths from header and lines (de-dup)
    seen = set()
    paths: List[str] = []
    for p in (header.get("auth_letter_paths") or []):
        if p and p not in seen:
            seen.add(p); paths.append(p)
    for ln in lines:
        p = (ln.get("details") or {}).get("auth_letter_path")
        if p and p not in seen:
            seen.add(p); paths.append(p)

    auth_links = []
    for p in paths:
        name = str(p).split("/")[-1]
        url = (public_prefix + str(p).lstrip("/")) if public_prefix else ""
        auth_links.append({
            "name": name,
            "url": url,
            "is_pdf": name.lower().endswith(".pdf"),
        })

    return render(request, "treasurer/detail.html", {
        "header": header,
        "status_ui": ui,
        "lines": lines,
        "payments": payments,
        "timeline": timeline,
        "methods": methods,
        "auth_links": auth_links,
    })


# ========== Take payment (POST) ==========
def take_payment(request: HttpRequest, doc_request_id: int):
    staff_id = 2  # TODO: pull from session/auth
    method_id = int(request.POST.get("payment_method_id", "0") or 0)
    amount_paid = Decimal(request.POST.get("amount_paid", "0") or "0")

    if amount_paid <= 0 or method_id <= 0:
        messages.error(request, "Enter a valid amount and payment method.")
        return redirect("treasurer:detail", doc_request_id=doc_request_id)

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

    or_id = res.data  # <-- INT or_id returned by the RPC

    # Fetch OR details for the toast
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

    return redirect("treasurer:detail", doc_request_id=doc_request_id)


# ========== Fees search + update ==========
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

    staff_id = 2
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
