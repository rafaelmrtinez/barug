from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Iterable
import io, os, zipfile, json, re
import traceback
from datetime import datetime, date, time
from decimal import Decimal
from django.forms import Form

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils import timezone
from django.conf import settings
from django.views.decorators.http import require_POST

from postgrest.exceptions import APIError
from django.views.decorators.http import require_GET

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase

from .forms import (
    SearchVerificationRequest, SearchBusinessOwner, BusinessOwnerInfo,
    BusinessDetails, BusinessFilters, RequestedDocsFilters, SelectOwnerForm
)

import logging

# ---- email helper (uses your custom Gmail SMTP backend) ----
from common.send_email import send_email

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

import logging
log = logging.getLogger(__name__)
from dataclasses import is_dataclass, asdict as dc_asdict
from django.views.decorators.csrf import csrf_protect
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
)
from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd
)

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

# =========================
# Logger + tiny debug helpers
# =========================
logger = logging.getLogger(__name__)

def _format_rcpt(rcpt: Any) -> str:
    try:
        if isinstance(rcpt, (list, tuple)) and len(rcpt) == 2:
            name, email = rcpt
            return f"{name} <{email}>" if name else str(email)
    except Exception:
        pass
    return str(rcpt)

def _debug_email_preview(subject: str, to_list: List[Any], body_txt: str, body_html: str | None):
    """Pretty-print what we're about to send (always prints; you can comment out if noisy)."""
    try:
        print("\n" + "=" * 72)
        print("[EMAIL DEBUG] Ready-for-pickup payload")
        print(f"Subject : {subject}")
        print(f"To      : {[ _format_rcpt(t) for t in to_list ]}")
        print("- TEXT ---------------------------------------------------")
        print(body_txt.rstrip())
        print("- HTML (first 600 chars) --------------------------------")
        snippet = (body_html or "")[:600]
        print(snippet.rstrip())
        if body_html and len(body_html) > 600:
            print("... [truncated]")
        print("=" * 72 + "\n")
    except Exception as e:
        logger.warning("Failed to print email preview: %s", e)

# =========================
# UI helpers / constants
# =========================
STATUS_UI: Dict[str, Dict[str, str]] = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "READY_FOR_PICKUP":     {"label": "Ready for Pickup",     "cls": "badge bg-warning-subtle text-warning-emphasis"},
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

# ---------------------------------------------------------------------
# Email-related helpers
# ---------------------------------------------------------------------
# --- add this helper near your email helpers ---

# --- add this helper near your email helpers ---
def _resolve_person_id_from_header(header: Dict[str, Any]) -> Optional[int]:
    """
    Find the most appropriate person_id in the header payload.
    Order:
      - requested_by_person_id (the requester)
      - on_behalf_of_person_id (if someone requested for someone else)
      - requester_person_id / subject_person_id / resident_person_id / person_id (fallbacks)
    """
    candidates = [
        header.get("requested_by_person_id"),
        header.get("on_behalf_of_person_id"),
        header.get("requester_person_id"),
        header.get("subject_person_id"),
        header.get("resident_person_id"),
        header.get("person_id"),
    ]
    for pid in candidates:
        if isinstance(pid, int) and pid > 0:
            return pid
    return None

def _send_ready_for_pickup_email(header: Dict[str, Any], lines: List[Dict[str, Any]]) -> Tuple[bool, str]:
    # resolve person id correctly (this was the bug)
    person_id = _resolve_person_id_from_header(header)
    print(f"[EMAIL DEBUG] resolved person_id from header -> {person_id!r}")

    full_name, email = _lookup_person_contact(person_id)
    if not email:
        print("[EMAIL DEBUG] no email found on file; skipping send.")
        return False, "No email on file for this resident. Notification not sent."

    req_code = header.get("request_code") or f"REQ-{header.get('doc_request_id','')}"
    doc_names = [(l.get("document_type_name") or "").strip() for l in (lines or [])]
    doc_names = [d for d in doc_names if d]
    docs_str = ", ".join(doc_names) if doc_names else "your requested document(s)"

    barangay_name = getattr(settings, "BRGY_NAME", "Barangay Sto. Niño")
    pickup_info  = getattr(settings, "BRGY_PICKUP_INFO", "Please proceed to the Barangay Office during office hours.")

    subject = f"{barangay_name}: Request {req_code} is READY FOR PICKUP"
    body_html = f"""
        <p>Hi {full_name or 'Resident'},</p>
        <p>Your barangay document request <strong>{req_code}</strong> is now
        <strong>READY FOR PICKUP</strong>.</p>
        <p><b>Document(s):</b> {docs_str}</p>
        <p>{pickup_info}</p>
        <p>Thank you,<br>{barangay_name}</p>
    """
    body_txt = (
        f"Hi {full_name or 'Resident'},\n\n"
        f"Your barangay document request {req_code} is now READY FOR PICKUP.\n"
        f"Documents: {docs_str}\n\n"
        f"{pickup_info}\n\n"
        f"Thank you,\n{barangay_name}\n"
    )
    to_list = [(full_name or "", email)]

    # show payload
    _debug_email_preview(subject, to_list, body_txt, body_html)

    try:
        result = send_email(
            subject=subject,
            to=to_list,
            body_text=body_txt,
            body_html=body_html,
            from_name=barangay_name,
            fail_silently=False,  # keep False until verified
        )
        print(f"[EMAIL DEBUG] send_email result -> ok={getattr(result,'ok',None)!r}, detail={getattr(result,'detail',None)!r}")
        return (True, f"Email notification sent to {email}.") if getattr(result, "ok", False) \
               else (False, "Failed to send email notification at this time.")
    except Exception as e:
        print(f"[EMAIL DEBUG] send_email raised: {e}")
        logger.exception("send_email raised")
        return False, f"Email not sent: {e}"



def _lookup_person_contact(person_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """Return (full_name, email) for a given person_id from the `person` table."""
    if not person_id:
        print("[EMAIL DEBUG] lookup: no person_id provided")
        return None, None
    try:
        res = (
            supabase
            .table("person")
            .select("first_name,last_name,email")
            .eq("person_id", person_id)
            .limit(1)
            .execute()
        )
        row = (res.data or [None])[0] or {}
        first = (row.get("first_name") or "").strip()
        last  = (row.get("last_name") or "").strip()
        full  = f"{first} {last}".strip() or None
        email = (row.get("email") or "").strip() or None

        # --- DEBUG print ---
        print(f"[EMAIL DEBUG] lookup person_id={person_id} -> full_name={full!r}, email={email!r}")
        return full, email
    except Exception as e:
        logger.exception("Lookup failed for person_id=%s", person_id)
        print(f"[EMAIL DEBUG] lookup failed for person_id={person_id}: {e}")
        return None, None


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
    print(f"[EMAIL DEBUG] mark_request_ready_for_pickup called for doc_request_id={doc_request_id}")
    # Fetch minimal details first for email context
    try:
        bundle = _fetch_bundle(doc_request_id)
    except APIError as e:
        print(f"[EMAIL DEBUG] _fetch_bundle failed: {e}")
        bundle = {"header": {}, "lines": []}

    header = bundle.get("header", {}) or {}
    lines  = bundle.get("lines", []) or []

    print(f"[EMAIL DEBUG] header keys: {list(header.keys())[:12]} ...")
    print(f"[EMAIL DEBUG] request_code={header.get('request_code')!r}, "
          f"requester_person_id={header.get('requester_person_id')!r}, "
          f"subject_person_id={header.get('subject_person_id')!r}")

    staff_id = _staff_id(request)
    reason = (request.POST.get("reason") or "").strip() or None
    print(f"[EMAIL DEBUG] RPC mark_request_ready_for_pickup -> staff_id={staff_id}, reason={reason!r}")

    res = supabase.rpc("mark_request_ready_for_pickup", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()

    if getattr(res, "error", None):
        print(f"[EMAIL DEBUG] RPC returned error: {res.error}")
        messages.error(request, f"Failed: {escape(res.error.message)}")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    print("[EMAIL DEBUG] RPC ok. Now sending email …")
    messages.success(request, "Marked as ready for pickup.")

    ok, info = _send_ready_for_pickup_email(header, lines)
    print(f"[EMAIL DEBUG] _send_ready_for_pickup_email -> ok={ok}, info={info!r}")
    if ok:
        messages.success(request, info)
    else:
        messages.info(request, info)

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

    parts = [
        (person.get("street") or "").strip(),
        (person.get("sitio_purok") or "").strip(),
        (person.get("barangay") or "").strip(),
        (person.get("city") or "").strip(),
    ]
    person["full_address"] = ", ".join([p for p in parts if p])

    status_row = get_verification_status_for_person(supabase, req_id)
    if status_row:
        person["latest_status"]  = status_row.get("status_text") or person.get("latest_status") or "Pending"
        person["remarks"]        = status_row.get("latest_remarks") or person.get("remarks")

    return render(request, "clerk/resident/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "person": person,
    })


# --- AJAX helpers (same file as your walk-in views) ---
from django.template.loader import render_to_string
from django.http import JsonResponse

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def ajax_purpose_options(request: HttpRequest):
    """Return <option> rows for a given request_document_type_id."""
    try:
        req_type_id = int(request.GET.get("request_document_type_id") or 0)
    except Exception:
        req_type_id = 0
    purposes = _fetch_purposes_by_request_type(req_type_id) if req_type_id else []
    html = render_to_string("clerk/doc_req/_purpose_options.html", {"purposes": purposes})
    return HttpResponse(html)


@session_login_required
@role_required(CLERK_ROLE)
@nocache
def ajax_resident_search(request: HttpRequest):
    """Debounced live search via RPC; returns an HTML fragment."""
    q = (request.GET.get("q") or "").strip()
    rows: List[Dict[str, Any]] = []
    if len(q) >= 2:
        try:
            res = supabase.rpc("search_person_by_code_or_name", {"p_key": q}).execute()
            rows = res.data or []
        except Exception as e:
            logger.warning("ajax_resident_search RPC failed: %s", e)
            rows = []

    html = render_to_string("clerk/doc_req/_resident_results.html", {"residents": rows})
    return HttpResponse(html)

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def ajax_purposes(request: HttpRequest):
    """Return the Purpose block for a given request_document_type_id (no page reload)."""
    try:
        req_type_id = int(request.GET.get("request_document_type_id") or 0)
    except Exception:
        req_type_id = 0

    purposes = _fetch_purposes_by_request_type(req_type_id) if req_type_id else []
    html = render_to_string("clerk/doc_req/_purpose_block.html", {
        "chosen_doc_type_id": req_type_id or None,
        "purposes": purposes,
    })
    return HttpResponse(html)

# =========================
# Walk-in Document Request (Clerk)
# =========================
# --- Walk-in Request (Clerk) — request_document_type-first --------------------
from typing import Any, Dict, List, Optional
import json

BRGY_BUSINESS_DOC_NAME = "BARANGAY BUSINESS CLEARANCE"  # must match your request_document_type_name

def _fetch_request_doc_types() -> List[Dict[str, Any]]:
    """
    Exactly mirrors the mobile `getDocumentTypes()`:
    request_document_type(request_document_type_id, request_document_type_name)
    """
    res = (
        supabase.table("request_document_type")
        .select("request_document_type_id, request_document_type_name")
        .order("request_document_type_name")
        .execute()
    )
    return res.data or []

def _fetch_purposes_by_request_type(req_doc_type_id: int) -> List[Dict[str, Any]]:
    """
    Mirrors mobile `getPurposesByDocumentType()`, but your `document_purpose`
    already carries fee_item_id & default fields (per screenshot).
    We join fee_item to expose flags and current_amount (used by the UI).
    """
    q = (
        supabase.table("document_purpose")
        .select(
            "document_purpose_id, request_document_type_id, purpose_code, purpose_label, "
            "default_details, default_offense_no, "
            "fee_item:fee_item_id(fee_item_id, current_amount, "
            "exempt_ftj, exempt_senior, exempt_pwd, exempt_indigent, exempt_student)"
        )
        .eq("request_document_type_id", req_doc_type_id)
        .order("purpose_label")
    ).execute()

    rows = q.data or []
    out: List[Dict[str, Any]] = []
    for r in rows:
        fi = r.get("fee_item") or {}
        out.append({
            "document_purpose_id": r["document_purpose_id"],
            "purpose_label": r.get("purpose_label"),
            "purpose_code": r.get("purpose_code"),
            "default_offense_no": r.get("default_offense_no"),
            "default_details": r.get("default_details") or {},
            "fee_item_id": fi.get("fee_item_id"),
            "current_amount": fi.get("current_amount") or 0,
            "exempt_ftj": bool(fi.get("exempt_ftj")),
            "exempt_senior": bool(fi.get("exempt_senior")),
            "exempt_pwd": bool(fi.get("exempt_pwd")),
            "exempt_indigent": bool(fi.get("exempt_indigent")),
            "exempt_student": bool(fi.get("exempt_student")),
        })
    return out

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def walkin_new(request: HttpRequest):
    """
    GET:
      - ?q= search residents
      - ?request_document_type_id= preselects doc type and loads purposes
    """
    q = (request.GET.get("q") or "").strip()

    # load document types for the dropdown
    doc_types = _fetch_request_doc_types()

    # selected request_document_type_id (if any)
    try:
        chosen_req_type_id = int(request.GET.get("request_document_type_id") or 0) or None
    except Exception:
        chosen_req_type_id = None

    purposes = _fetch_purposes_by_request_type(chosen_req_type_id) if chosen_req_type_id else []

    # simple resident search
    residents: List[Dict[str, Any]] = []
    if q:
        like = f"%{q}%"
        res = (
            supabase.table("person")
            .select("person_id, person_code, first_name, last_name, email")
            .or_(f"first_name.ilike.{like},last_name.ilike.{like},person_code.ilike.{like}")
            .limit(30)
            .execute()
        )
        residents = res.data or []

    return render(request, "clerk/walkin_request.html", {
        "q": q,
        "doc_types": doc_types,
        "chosen_doc_type_id": chosen_req_type_id,  # template uses this name
        "purposes": purposes,
        "residents": residents,
    })

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def walkin_create(request: HttpRequest):
    """
    POST handler that builds the same payload the mobile sends into
    `create_document_request`.
    """
    # 1) Subject / requester
    try:
        requested_by = int(request.POST.get("requested_by_person_id") or 0)
    except Exception:
        requested_by = 0

    is_on_behalf_flag = (request.POST.get("is_on_behalf") == "on")
    try:
        on_behalf_of = int(request.POST.get("on_behalf_of_person_id") or 0) or None
    except Exception:
        on_behalf_of = None

    subject_id = on_behalf_of if (is_on_behalf_flag and on_behalf_of) else requested_by
    is_on_behalf = bool(subject_id and requested_by and subject_id != requested_by)

    # 2) Optional business
    try:
        business_id = int(request.POST.get("business_id") or 0) or None
    except Exception:
        business_id = None

    purpose_notes = (request.POST.get("purpose_notes") or "").strip() or None

    # 3) Lines (match mobile names)
    try:
        req_doc_type_id = int(request.POST.get("request_document_type_id") or 0) or None
    except Exception:
        req_doc_type_id = None

    dp_ids = request.POST.getlist("line_document_purpose_id[]") or []
    qtys   = request.POST.getlist("line_quantity[]") or []
    offs   = request.POST.getlist("line_offense_no[]") or []

    if not requested_by:
        messages.error(request, "Please select a resident first (Requester).")
        return redirect("clerk:walkin_new")

    if not req_doc_type_id or not dp_ids:
        messages.error(request, "Please choose a document and a purpose.")
        return redirect(f"{request.path.replace('/create/','/')}?request_document_type_id={req_doc_type_id or ''}")

    # Map document_purpose_id -> meta (for purpose_code & defaults)
    purpose_rows = {
        r["document_purpose_id"]: r
        for r in _fetch_purposes_by_request_type(req_doc_type_id)
    }

    lines: List[Dict[str, Any]] = []
    for i, raw_dp in enumerate(dp_ids):
        try:
            dp_id = int(raw_dp)
        except Exception:
            continue

        qty = 1
        try:
            qty = max(1, int(qtys[i]))
        except Exception:
            pass

        offense_no = None
        try:
            offense_no = int(offs[i]) if offs[i] else None
        except Exception:
            offense_no = None

        meta = purpose_rows.get(dp_id) or {}
        details: Dict[str, Any] = {}

        # persist purpose_code so the PDF/receipts can show it later
        if meta.get("purpose_code"):
            details["purpose_code"] = meta["purpose_code"]

        # allow defaults to flow through (e.g., residency_kind, etc.)
        if meta.get("default_details"):
            details.update(meta["default_details"] or {})

        lines.append({
            "document_purpose_id": dp_id,
            "quantity": qty,
            "offense_no": offense_no,
            "details": details,
        })

    # Optional soft warning for Business Clearance without business_id
    try:
        dt = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .eq("request_document_type_id", req_doc_type_id)
            .limit(1)
            .execute()
        )
        name = ((dt.data or [{}])[0] or {}).get("request_document_type_name") or ""
        if name == BRGY_BUSINESS_DOC_NAME and not business_id:
            messages.warning(request, "Business ID is empty for Business Clearance. Treasurer may reject.")
    except Exception:
        pass

    payload = {
        "requested_by": requested_by,
        "on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
        "is_on_behalf": is_on_behalf,
        "business_id": business_id,
        "purpose_notes": purpose_notes,
        "lines": lines,
    }

    # --- DEBUG: show exactly what we will send (client-shape) ---
    print("\n[WALKIN DEBUG] (client-shape) create_document_request payload:\n",
        json.dumps({
            "requested_by": requested_by,
            "on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
            "is_on_behalf": is_on_behalf,
            "business_id": business_id,
            "purpose_notes": purpose_notes,
            "lines": lines,
        }, indent=2))

    # --- CALL THE RPC WITH THE NAMES YOUR FUNCTION EXPECTS ---
    rpc_args = {
        "p_requested_by": requested_by,
        "p_on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
        "p_is_on_behalf": is_on_behalf,
        "p_business_id": business_id,
        "p_purpose_notes": purpose_notes,
        "p_lines": lines,  # supabase client will JSON-encode this list into jsonb
    }

    print("[WALKIN DEBUG] (rpc-shape) args sent to create_document_request:\n",
        json.dumps(rpc_args, indent=2, default=str))

    try:
        res = supabase.rpc("create_document_request", rpc_args).execute()
        print("[WALKIN DEBUG] RPC result .data :", getattr(res, "data", None))
        print("[WALKIN DEBUG] RPC result .error:", getattr(res, "error", None))
    except Exception as e:
        print("[WALKIN DEBUG] RPC raised:", e)
        messages.error(request, f"RPC failed: {e}")
        return redirect("clerk:walkin_new")

    # Supabase can return a scalar or a 1-row list depending on driver
    if getattr(res, "error", None):
        messages.error(request, f"Supabase error: {escape(res.error.message)}")
        return redirect("clerk:walkin_new")

    data = res.data
    new_id = None
    if isinstance(data, list) and data:
        new_id = data[0]
    elif isinstance(data, dict) and "doc_request_id" in data:
        new_id = data["doc_request_id"]
    else:
        # plain scalar int
        new_id = data

    if not new_id:
        messages.error(request, "Could not obtain new request ID from RPC.")
        return redirect("clerk:walkin_new")

    messages.success(request, f"Walk-in request created. ID: {new_id}")
    return redirect("clerk:detail", doc_request_id=new_id)



# =========================
# Business screens (stubs; clerk-only)
# =========================
def _auth_staff_id(request: HttpRequest) -> Optional[int]:
    return ((request.session.get("auth") or {}).get("staff_id")) or None

def _sstrip(v: Any) -> Optional[str]:
    """Strip only if string; return None for empty strings; pass through other types."""
    if v is None:
        return None
    if isinstance(v, str):
        t = v.strip()
        return t or None
    return v  # keep non-strings as-is

def _to_str_num(v: Any, default: str = "0") -> str:
    """Convert Decimal/int/float to string for session JSON safety."""
    if v is None or v == "":
        return default
    try:
        return str(v)
    except Exception:
        return default

def _to_float_or_none(val) -> Optional[float]:
    try:
        if val in (None, "", "None"):
            return None
        return float(val)
    except Exception:
        return None

def _to_int_or_none(val) -> Optional[int]:
    try:
        if val in (None, "", "None"):
            return None
        return int(val)
    except Exception:
        return None

def _parse_date_iso(s: Any) -> Any:
    if isinstance(s, date):
        return s
    if isinstance(s, str) and s:
        try:
            return date.fromisoformat(s)
        except ValueError:
            return s
    return s

def _parse_time_hms(s: Any) -> Any:
    if isinstance(s, time):
        return s
    if isinstance(s, str) and s:
        try:
            parts = s.split(":")
            if len(parts) == 2:
                h, m = parts
                return time(int(h), int(m), 0)
            elif len(parts) == 3:
                h, m, sec = parts
                return time(int(h), int(m), int(sec))
        except Exception:
            return s
    return s

def _fmt_peso(v: Any) -> str:
    # We stored money-like values as strings earlier; accept Decimal/float/string
    if v in (None, "", "None"):
        return "₱ 0.00"
    try:
        num = float(v) if not isinstance(v, (int, float)) else v
        return f"₱ {num:,.2f}"
    except Exception:
        return f"₱ {v}"

def _json_safe(val):
    """Recursively convert Decimals, dates, times, etc. to JSON-serializable types."""
    if isinstance(val, Decimal):
        # choose float for numbers (you already stringified money fields separately)
        return float(val)
    if isinstance(val, (list, tuple)):
        return [ _json_safe(v) for v in val ]
    if isinstance(val, dict):
        return { k: _json_safe(v) for k, v in val.items() }
    # dates/times in your code are already converted to isoformat or HH:MM:SS
    return val

def _owner_full_name(o: dict) -> str:
    last = (o.get("last_name") or "").strip()
    first = (o.get("first_name") or "").strip()
    mid = (o.get("middle_name") or "").strip()
    suffix = (o.get("suffix") or "").strip()
    parts: List[str] = []
    if last: parts.append(last.upper())
    if first: parts.append(", " + first.title())
    if mid: parts.append(" " + (mid[0].upper() + "."))
    if suffix: parts.append(" " + suffix.upper())
    if parts:
        return "".join(parts)
    # 🔽 DTO fallback
    fn = (o.get("full_name") or "").strip()
    return fn or "—"

def _join_addr(parts: List[str]) -> str:
    return ", ".join([p.strip() for p in parts if p and p.strip()])

def _choices_to_map(choices: Iterable) -> Dict[Any, str]:
    """
    Convert Django choices (which may include optgroups) to {value: label}.
    Safely handles:
      - [("", "— Select —"), (1, "ONE"), (2, "TWO")]
      - [("WEEKDAYS", [(1,"Mon"), (2,"Tue")]), ("WEEKEND", [(6,"Sat"), (7,"Sun")])]
    """
    out: Dict[Any, str] = {}
    for item in choices or []:
        # Optgroup: (group_label, list_of_choices)
        if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[1], (list, tuple)):
            _group_label, _group_choices = item
            for v, lbl in _group_choices:
                out[_coerce_key(v)] = str(lbl)
        else:
            # Regular choice: (value, label)
            try:
                v, lbl = item
                out[_coerce_key(v)] = str(lbl)
            except Exception:
                continue
    return out

def _coerce_key(v: Any) -> Any:
    """Try to turn numeric-looking keys into int for easy matching; else leave as-is."""
    if v is None:
        return None
    # If already an int, or your TypedChoiceField coerces to int, this keeps it as int.
    if isinstance(v, int):
        return v
    # Try to int-ify strings like "1"
    try:
        return int(v)
    except Exception:
        return v  # keep original (e.g., "" for blank choice)

def _field_map(form: Form, field_name: str) -> Dict[Any, str]:
    field = form.fields.get(field_name)
    if not field:
        return {}
    return _choices_to_map(field.choices)

def fetch_display_maps_from_forms() -> Dict[str, Dict[Any, str]]:
    """
    Build all needed {id: label} maps directly from your static Django forms.
    Adjust field names if yours differ.
    """
    from .forms import BusinessOwnerInfo, BusinessDetails  # import here to avoid circulars
    owner_form = BusinessOwnerInfo()
    biz_form = BusinessDetails()

    return {
        # Owner-side lookups
        "sex": _field_map(owner_form, "sex"),
        "civil_status": _field_map(owner_form, "civil_status"),
        "nationality": _field_map(owner_form, "nationality"),
        "religion": _field_map(owner_form, "religion"),

        # Business-side lookups
        "business_type": _field_map(biz_form, "b_type"),
        "ownership_type": _field_map(biz_form, "ownership_type"),
        "business_category": _field_map(biz_form, "b_category"),

        # Operating day labels (fallback if one is missing)
        "operating_day": _field_map(biz_form, "opt_days_start") or _field_map(biz_form, "opt_days_end"),
    }

def build_owner_display(owner: dict, maps: Dict[str, Dict[Any, str]]) -> Dict[str, Any]:
    sex_name = (
        owner.get("sex_name")
        or maps.get("sex", {}).get(owner.get("sex_id"))
        or owner.get("sex")
    )
    civil_name = (
        owner.get("civil_status_name")
        or owner.get("civil_status")
        or maps.get("civil_status", {}).get(owner.get("civil_status_id"))
        or owner.get("civil_status_id")
    )
    nat_name = (
        owner.get("nationality_name")
        or owner.get("nationality")
        or maps.get("nationality", {}).get(owner.get("nationality_id"))
        or owner.get("nationality_id")
    )
    rel_name = (
        owner.get("religion_name")
        or owner.get("religion")
        or maps.get("religion", {}).get(owner.get("religion_id"))
        or owner.get("religion_id")
    )

    full_name = _owner_full_name(owner)
    addr = _join_addr([
        owner.get("street") or "",
        owner.get("purok_sitio") or "",
        owner.get("barangay") or "",
        owner.get("city") or "",
    ])

    # 👇 normalize for display even if session is old and lacks the field
    res_name = _normalize_residency_name(
        owner.get("residency_name") or owner.get("residential_status_name")
    )

    return {
        "full_name": full_name,
        "person_code": owner.get("person_code"),
        "sex_name": sex_name or "—",
        "dob": owner.get("dob") or owner.get("date_of_birth") or "—",
        "civil_status_name": civil_name or "—",
        "nationality_name": nat_name or "—",
        "religion_name": rel_name or "—",
        "mobile": owner.get("mobile") or "—",
        "email": owner.get("email") or "—",
        "address_display": addr or (owner.get("address_line") or "—"),
        "residency_name": res_name,  # 👈 always a value
    }

def build_business_display(biz: dict, maps: Dict[str, Dict[int, str]]) -> Dict[str, Any]:
    """
    Return a label-rich dict strictly for display.
    """
    btype_name = maps.get("business_type", {}).get(biz.get("b_type")) or biz.get("b_type_name")
    owner_type_name = maps.get("ownership_type", {}).get(biz.get("ownership_type")) or biz.get("ownership_type_name")
    cat_name = maps.get("business_category", {}).get(biz.get("b_category")) or biz.get("b_category_name")  # 👈 NEW

    # Operating day labels from form choices (fallback to raw if missing)
    day_map = maps.get("operating_day", {}) or {}
    opt_days_start_lbl = day_map.get(biz.get("opt_days_start")) or biz.get("opt_days_start")
    opt_days_end_lbl   = day_map.get(biz.get("opt_days_end"))   or biz.get("opt_days_end")

    addr = _join_addr([
        biz.get("street") or "",
        biz.get("purok_sitio") or "",
        biz.get("barangay") or "",
        biz.get("city") or "",
    ])

    return {
        "b_name": biz.get("b_name") or "—",
        "b_type_name": btype_name or biz.get("b_type") or "—",
        "b_nature": biz.get("b_nature") or "—",
        "ownership_type_name": owner_type_name or biz.get("ownership_type") or "—",
        "b_category_name": cat_name or biz.get("b_category") or "—",  # 👈 NEW (label-first, raw fallback)
        "b_category": biz.get("b_category"),                           # 👈 NEW (raw id)

        "address_display": addr or "—",
        "latitude": biz.get("latitude"),
        "longitude": biz.get("longitude"),
        "b_desc": biz.get("b_desc") or "—",
        "date_est": biz.get("date_est") or "—",
        "dti": biz.get("dti") or "—",
        "capital_display": _fmt_peso(biz.get("capital_invested")),
        "prevgross_display": _fmt_peso(biz.get("prevgross")),
        "inc_est": _fmt_peso(biz.get("inc_est")),
        "employees_display": biz.get("emp_num") or "—",

        # expose both label and raw for completeness
        "opt_days_start_name": opt_days_start_lbl,
        "opt_days_end_name": opt_days_end_lbl,
        "opt_days_start": biz.get("opt_days_start"),
        "opt_days_end": biz.get("opt_days_end"),
        "opt_start": biz.get("opt_start"),
        "opt_end": biz.get("opt_end"),
        "proof_name": biz.get("proof_name") or "—",
    }

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

# def _to_int_or_none(val: str | None) -> int | None:
#     if val is None:
#         return None
#     s = str(val).strip()
#     if not s:
#         return None
#     try:
#         return int(s)
#     except ValueError:
#         return None
    
def _normalize_owner_rows(rows):
    """
    Normalize DTOs/objects into dicts the template & AJAX both expect.
    """
    payload = []
    for r in rows or []:
        if isinstance(r, dict):
            d = r
        elif is_dataclass(r):
            d = dc_asdict(r)
        elif hasattr(r, "_asdict"):
            try:
                d = r._asdict()
            except Exception:
                d = getattr(r, "__dict__", {}) or {}
        else:
            d = getattr(r, "__dict__", {}) or {}

        payload.append({
            "person_id": d.get("person_id"),
            "person_code": d.get("person_code") or "",
            "person_name": d.get("full_name") or d.get("person_name") or "",
            "street": d.get("street") or "",
            "purok": d.get("purok") or "",
            "barangay": d.get("barangay") or "",
            "city": d.get("city") or "",
            # optional extras if your SQL provides them
            "sex_name": d.get("sex_name") or "",
            "date_of_birth": d.get("date_of_birth") or "",
            "residential_status_name": d.get("residential_status_name") or "",
            "address_line": d.get("address_line") or "",
        })
    return payload

def _asdict_loose(obj: Any) -> Dict[str, Any]:
    """Return a plain dict from dataclass / namedtuple / dict / generic object."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return dc_asdict(obj)
    if hasattr(obj, "_asdict"):
        try:
            return obj._asdict()
        except Exception:
            pass
    out: Dict[str, Any] = {}
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except Exception:
            continue
        if callable(v):
            continue
        out[k] = v
    return out

def _normalize_residency_name(s: Optional[str]) -> str:
    if not s:
        return "NON-RESIDENT"
    x = (str(s) or "").strip().upper()
    if x in {"RESIDENT", "R"}: return "RESIDENT"
    if x in {"NON RESIDENT", "NON-RESIDENT", "NONRESIDENT", "NR"}: return "NON-RESIDENT"
    if x in {"TRANSIENT", "T"}: return "TRANSIENT"
    return x or "NON-RESIDENT"

def _owner_payload_common_from_dict(src: Any) -> Dict[str, Any]:
    d = _asdict_loose(src)

    dob_val = d.get("dob") or d.get("date_of_birth")
    if isinstance(dob_val, date):
        dob_str = dob_val.isoformat()
    elif isinstance(dob_val, str):
        dob_str = dob_val
    else:
        dob_str = None

    payload = {
        "owner_person_id": _to_int_or_none(d.get("owner_person_id") or d.get("person_id")),
        # keep split names if available + full_name for display fallback
        "last_name": _sstrip(d.get("last_name")) or "",
        "first_name": _sstrip(d.get("first_name")) or "",
        "middle_name": _sstrip(d.get("middle_name")),
        "suffix": _sstrip(d.get("suffix")),
        "full_name": _sstrip(d.get("full_name")),

        "dob": dob_str,
        "email": _sstrip(d.get("email")),
        "mobile": _sstrip(d.get("mobile") or d.get("mob_num")),

        # IDs if you ever have them (DTO strings will not coerce to int)
        "sex_id": _to_int_or_none(d.get("sex_id") or d.get("sex")),
        "civil_status_id": _to_int_or_none(d.get("civil_status_id")),
        "nationality_id": _to_int_or_none(d.get("nationality_id")),
        "religion_id": _to_int_or_none(d.get("religion_id")),

        # 🔽 carry human-readable labels from DTO
        "sex_name": _sstrip(d.get("sex_name")),
        "civil_status_name": _sstrip(d.get("civil_status")),
        "nationality_name": _sstrip(d.get("nationality")),
        "religion_name": _sstrip(d.get("religion")),

        # address
        "street": _sstrip(d.get("street")) or "",
        "purok_sitio": _sstrip(d.get("purok_sitio") or d.get("purok")) or "",
        "barangay": _sstrip(d.get("barangay")) or "",
        "city": _sstrip(d.get("city")) or "",
        "address_line": _sstrip(d.get("address_line")),  # optional fallback for display

        "person_code": _sstrip(d.get("person_code")),
        "residency_name": _normalize_residency_name(d.get("residency_name") or d.get("residential_status_name") or "NON-RESIDENT"),
    }
    return payload

@session_login_required
@role_required(CLERK_ROLE)
@csrf_protect
@nocache
@inject
def business_owner_resident(
    request: HttpRequest,
    resident_owner_service: IResidentOwnerService = Provide[AppContainer.resident_owner_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    """
    Page render:
      - preserves server-side render if `?search=` is present
      - front-end enhances with AJAX type-ahead
    """
    user_role = _auth_role_name(request)
    form = SearchBusinessOwner(request.GET or None)
    select_form = SelectOwnerForm(request.POST or None)

    search = (request.GET.get("search") or request.POST.get("search") or "").strip()

    rows: List[Dict[str, Any]] = []
    if search:
        try:
            rows = resident_owner_service.execute(search=search) or []
        except Exception:
            log.exception("Owner search failed for %r", search)  # <-- keep a trace
            rows = []

    results_payload = _normalize_owner_rows(rows)

    selected: dict | None = None
    if request.method == "POST" and select_form.is_valid():
        try:
            owner_id = int(select_form.cleaned_data["owner_person_id"])
            selected = resident_owner_service.get_owner_details(owner_id)
        except Exception:
            log.exception("Fetching owner details failed for id=%s", request.POST.get("owner_person_id"))
            selected = None

    if selected:
        owner_payload = _owner_payload_common_from_dict(selected)

        request.session["bizreg_owner"] = owner_payload
        request.session.set_expiry(1800)

        messages.success(request, "Owner selected. Continue with business details.")

    # keep form pristine if invalid
    if search and not form.is_valid():
        form = SearchBusinessOwner()

    return render(
        request,
        "business/business_owner_resident.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "form": form,
            "select_form": select_form,
            "search": search,           # single source of truth (no 'q')
            "results": results_payload, # server-rendered initial list (optional)
            "selected": selected,
        },
    )

@require_GET
@inject
def ajax_owner_search(
    request: HttpRequest,
    resident_owner_service: IResidentOwnerService = Provide[AppContainer.resident_owner_service],
):
    """
    AJAX endpoint for live search.
    Expects: ?search=<term>
    Returns: {"results": [ ...normalized rows... ]}
    """
    search = (request.GET.get("search") or "").strip()
    if not search:
        return JsonResponse({"results": []})

    try:
        rows = resident_owner_service.execute(search=search) or []
    except Exception:
        rows = []

    payload = _normalize_owner_rows(rows)
    return JsonResponse({"results": payload})

@session_login_required
@role_required(CLERK_ROLE)
@csrf_protect
@nocache
def business_owner_nonresident(request: HttpRequest) -> HttpResponse:
    user_role = _auth_role_name(request)

    if request.method == "POST":
        form = BusinessOwnerInfo(request.POST)
        if form.is_valid():

            dob_val = form.cleaned_data["dob"]
            dob_str = dob_val.isoformat() if isinstance(dob_val, date) else str(dob_val)

            owner_payload: Dict[str, Any] = {
                "owner_person_id": form.cleaned_data.get("owner_person_id") or None,
                "last_name": form.cleaned_data["last_name"].strip(),
                "first_name": form.cleaned_data["first_name"].strip(),
                "middle_name": (form.cleaned_data.get("middle_name") or "").strip() or None,
                "suffix": (form.cleaned_data.get("suffix") or "").strip() or None,
                # ensure your form field is named 'dob' and is a DateField or "YYYY-MM-DD" string
                "dob": dob_str,
                "email": (form.cleaned_data.get("email") or "").strip() or None,
                "mobile": (form.cleaned_data.get("mob_num") or "").strip() or None,
                "sex_id": int(form.cleaned_data["sex"]),
                "civil_status_id": int(form.cleaned_data["civil_status"]),
                "nationality_id": int(form.cleaned_data["nationality"]),
                "religion_id": int(form.cleaned_data["religion"]),
                "street": form.cleaned_data["street"].strip(),
                "purok_sitio": (form.cleaned_data.get("purok_sitio") or "").strip(),
                "barangay": form.cleaned_data["barangay"].strip(),
                "city": form.cleaned_data["city"].strip(),
            }

            # Store and expire in 30 minutes
            request.session["bizreg_owner"] = owner_payload
            request.session.set_expiry(1800)
            owner_payload["residency_name"] = "NON-RESIDENT"
            # Optional success flash
            messages.success(request, "Owner info saved. Continue with business details.")

            # Redirect to the next step (ensure this URL name exists)
            return redirect("clerk:business_details")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # GET — prefill from session if present; convert dob string back to a date for the DateField
        saved = request.session.get("bizreg_owner") or {}
        if "dob" in saved and isinstance(saved["dob"], str):
            try:
                saved["dob"] = date.fromisoformat(saved["dob"])
            except ValueError:
                # leave as-is if parsing fails; the form will show the raw string
                pass
        form = BusinessOwnerInfo(initial=saved or None)

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

    owner = request.session.get("bizreg_owner")
    if not owner:
        messages.warning(request, "No owner info found. Please fill the form first.")
        return redirect("clerk:business_owner_nonresident")
    
    if request.method == "POST":
        form = BusinessDetails(request.POST, request.FILES or None)

        if form.is_valid():
            cd = form.cleaned_data

            # Build a JSON-serializable payload for session
            payload: Dict[str, Any] = {
                # strings → strip safely
                "b_name": _sstrip(cd.get("b_name")) or "",
                "b_nature": _sstrip(cd.get("b_nature")),
                "b_address": _sstrip(cd.get("b_address")) or "",
                "b_desc": _sstrip(cd.get("b_desc")),
                "dti": _sstrip(cd.get("dti")),
                "inc_est": _sstrip(cd.get("inc_est")),

                # choice/ids
                "b_type": _to_int_or_none(cd.get("b_type")),
                "ownership_type": _to_int_or_none(cd.get("ownership_type")),
                "b_category": _to_int_or_none(cd.get("b_category")),

                # numbers (keep JSON-safe as strings)
                "capital_invested": _to_str_num(cd.get("capital_invested"), "0"),
                "prevgross": _to_str_num(cd.get("prevgross"), "0"),
                "emp_num": _to_int_or_none(cd.get("emp_num") or 0),

                # days/time
                "opt_days_start": _to_int_or_none(cd.get("opt_days_start")),
                "opt_days_end": _to_int_or_none(cd.get("opt_days_end")),
                "opt_start": cd["opt_start"].strftime("%H:%M:%S") if cd.get("opt_start") else None,
                "opt_end": cd["opt_end"].strftime("%H:%M:%S") if cd.get("opt_end") else None,

                # date
                "date_est": (cd["date_est"].isoformat() if cd.get("date_est") else None),

                # geo
                "latitude": _to_float_or_none(cd.get("latitude")),
                "longitude": _to_float_or_none(cd.get("longitude")),

                # address modal fields (strings)
                "street": _sstrip(cd.get("street")) or "",
                "purok_sitio": _sstrip(cd.get("purok_sitio")) or "",
                "barangay": _sstrip(cd.get("barangay")) or "",
                "city": _sstrip(cd.get("city")) or "",
            }

            # NOTE: We intentionally DO NOT put file objects (e.g., proof) in session.
            if request.FILES.get("proof"):
                payload["proof_name"] = request.FILES["proof"].name  # just for display; not the file itself
            
            payload = _json_safe(payload)

            request.session["bizreg_business"] = payload
            request.session.set_expiry(1800)  # 30 minutes

            messages.success(request, "Business details saved.")
            return redirect("clerk:business_information_review")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        saved = request.session.get("bizreg_business") or {}

        # Convert back to proper field types for form initial
        if "date_est" in saved:
            saved["date_est"] = _parse_date_iso(saved["date_est"])
        if "opt_start" in saved:
            saved["opt_start"] = _parse_time_hms(saved["opt_start"])
        if "opt_end" in saved:
            saved["opt_end"] = _parse_time_hms(saved["opt_end"])

        form = BusinessDetails(initial=saved or None)

    return render(
        request,
        "business/business_details.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
            "page_title": "Business Information",
            "form": form,
            "owner": owner,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
@inject
def business_information_review(
    request: HttpRequest,
    business_registration_service: IBusinessRegistrationService = Provide[AppContainer.business_registration_service],
):
    user_role = _auth_role_name(request)

    owner = request.session.get("bizreg_owner")
    if not owner:
        return redirect("clerk:business_owner_nonres")

    business = request.session.get("bizreg_business")
    if not business:
        return redirect("clerk:business_details")
    
    if request.method == "POST":
        action = (request.POST.get("action") or "").lower()
        if action == "confirm_add":
            # Accept single or multiple files (template may use name="proof")
            uploads = []
            if "proof" in request.FILES:
                # getlist works even if single file
                uploads = request.FILES.getlist("proof")

            cmd = RegisterBusinessProfileCmd(
                owner=owner,
                business=business,
                performer_staff_id=_auth_staff_id(request),
                proof_files_uploads=uploads,
            )

            try:
                business_id, owner_person_id = business_registration_service.business_registration(cmd)
                request.session.pop("bizreg_owner", None)
                request.session.pop("bizreg_business", None)
                messages.success(request, f'Business #{business_id} created for owner #{owner_person_id}.')
                return redirect("clerk:business_list")
            except Exception as e:
                print("[business_information_review] Failed to register business:", e, flush=True)
                traceback.print_exc()
                messages.error(request, f"Failed to register business: {e}")
                return redirect("clerk:business_information_review")

    
     # Normalize a few fields for nicer display on the review page
    owner = dict(owner)  # shallow copy so we can tweak for display
    if "dob" in owner:
        owner["dob"] = _parse_date_iso(owner["dob"])

    business = dict(business)
    if "date_est" in business:
        business["date_est"] = _parse_date_iso(business["date_est"])
    if "opt_start" in business:
        business["opt_start"] = _parse_time_hms(business["opt_start"])
    if "opt_end" in business:
        business["opt_end"] = _parse_time_hms(business["opt_end"])

    maps = fetch_display_maps_from_forms()
    owner_disp = build_owner_display(owner, maps)
    biz_disp   = build_business_display(business, maps)

        
    return render(
        request,
        "business/business_information_review.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
            "page_title": "Business Information",
            "owner": owner,                 # raw for future DB insert
            "business": business,           # raw for future DB insert
            "owner_disp": owner_disp,       # labels for display
            "biz_disp": biz_disp,           # labels for display
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@csrf_protect
@nocache
@inject
def business_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_type = _to_int_or_none(request.GET.get("b_type"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search= search,
        b_type= b_type,
        ownership_type= ownership_type,
        status= status,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_type is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(request, "business/business_list.html", {
        'page_path': f'{user_role} / Business Records',
        'page_title': 'Business Records',
        'form' : form,
        'page_obj' : page_obj,
        'filters' : {
            'search' : search,
            'b_type' : b_type,
            'ownership_type' :ownership_type,
            'status' : status,
        }
    })

@inject
def ajax_business_search(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    # only allow XHR (optional, but nice)
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR required")

    q = request.GET.get("q", "") or None
    b_type = request.GET.get("b_type")
    ownership_type = request.GET.get("ownership_type")
    status = request.GET.get("status")

    def to_int_or_none(v):
        try:
            return int(v) if v not in (None, "",) else None
        except ValueError:
            return None

    rows = business_service.execute(
        search=q,
        b_type=to_int_or_none(b_type),
        ownership_type=to_int_or_none(ownership_type),
        status=to_int_or_none(status),
    )

    # If you want to cap results for live list:
    rows = rows[:50]

    html = render_to_string("business/_business_list.html", {"rows": rows}, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_information(request: HttpRequest, b_id: int):
    user_role = _auth_role_name(request)
    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {b_id}",
            "page_title": f"Business Details : {b_id}",
        },
    )

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
