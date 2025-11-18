# ============================================================ 
# views.py — Clerk flows + Printing with Business Clearance map
# ============================================================

from __future__ import annotations

# ────────────────────────────────────────────────────────────
# SECTION: Imports
# ────────────────────────────────────────────────────────────
import datetime as dt
import copy
from uuid import uuid4
from typing import Any, Dict, List, Optional, Tuple, Iterable
import io, os, zipfile, json, re
from datetime import datetime
from decimal import Decimal
import logging
import traceback
import uuid
from datetime import datetime, date, time

from decimal import Decimal
from django.forms import Form
from django.urls import reverse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils import timezone
from django.conf import settings
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.http import JsonResponse

from postgrest.exceptions import APIError
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase

from urllib.parse import quote as urlquote
from django.db import connection

from .forms import (
    SearchVerificationRequest, SearchBusinessOwner, SelectOwnerForm , BusinessOwnerInfo,
    BusinessDetails, BusinessFilters, RequestedDocsFilters, SelectOwnerForm, RenewalFilters
)

# ---- email helper (uses your custom Gmail SMTP backend) ----
from common.send_email import send_email

# ---- services (PDF, request bundles, subject resolver, ID verification) ----
# existing imports above…

from .services.requests_service import (
    _fetch_bundle,
    _set_status,
    confirm_and_send_to_printing,
    confirm_forward_treasurer as svc_confirm_forward_treasurer,
)

from .services.subject_service import subject_view
from .services.pdf_service import (
    _pdf_templates_dir, _get_all_pdf_field_names, _fill_pdf_with_values,
    _choose_template, _safe_str, _fill_fields_for_line,
    BUSINESS_CLEARANCE_FIELD_MAP,  # field map from pdf_service
)
from .services.id_verification_service import (
    fetch_id_verification_requests,
    get_verification_status_for_person,
)

from treasurer.services.requests_service import build_auth_links


def titleize(s):
    txt = str(s or "")
    return " ".join(txt.replace("_", " ").replace("-", " ").split()).title()

def _norm(s) -> str:
    """UPPER_CASE_WITH_UNDERSCORES normalizer for statuses/actions."""
    return re.sub(r"[\s_]+", "_", str(s or "").strip().upper())

# ────────────────────────────────────────────────────────────
# SECTION: Logger + tiny email preview helpers
# ────────────────────────────────────────────────────────────
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
    IBusinessInfoService,
    INonResidentOwnerService,
    IBusinessRenewalService,
    IBusinessRenewalQuoteService,
    IBusinessRenewalRequestService,
    IBusinessClosurePaymentRequestService,
)
from src.domain.contracts.business_repository_contract import IBusinessRepository
from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd,
    CreateRenewalRequestCmd,
)
from src.app.services.business_notification import notify_registration_received
from common.send_sms import send_sms

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
    """Pretty-print what we're about to send."""
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

# ────────────────────────────────────────────────────────────
# SECTION: UI constants
# ────────────────────────────────────────────────────────────
STATUS_UI: Dict[str, Dict[str, str]] = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "FOR CLERK REVIEW":     {"label": "For Clerk Review",     "cls": "badge bg-secondary-subtle text-secondary-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "READY_FOR_PICKUP":     {"label": "Ready for Pickup",     "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}
# include clerk-review in default list shown on queue if you want
CLERK_STATUSES_ALL = ["FOR CLERK REVIEW", "PAID", "FOR_PRINTING", "RELEASED", "DECLINED"]
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

# ────────────────────────────────────────────────────────────
# SECTION: Business Clearance constants
# ────────────────────────────────────────────────────────────
BRGY_BUSINESS_DOC_NAME = "BARANGAY BUSINESS CLEARANCE"     # must match request_document_type_name
BRGY_BUSINESS_PDF_FILE = "barangay-business-clearance.pdf" # the uploaded template filename
# e.g., near BRGY_BUSINESS_DOC_NAME / BRGY_BUSINESS_PDF_FILE
CTC_BRGY_BUSINESS_PDF_FILE = "ctc-barangay-business-clearance.pdf"

# ────────────────────────────────────────────────────────────
# SECTION: Missing-value advice (for logs)
# ────────────────────────────────────────────────────────────
_BC_ADVICE: Dict[str, str] = {
    "applicant_full_name":   "Pull from person(first_name,last_name) where person_id = subject_person_id (or requested_by).",
    "applicant_age":         "Compute from person.birthdate (see _age_from_birthdate).",
    "applicant_nationality": "Join person.nationality_id → nationality.nationality_name.",
    "business_name_style":   "From business.business_name for the selected business_id.",
    "business_address":      "From business.address_id → address(street,purok_sitio,barangay,city).",
    "capital_invested":      "From business.capital_invested.",
    "gross_sales_prev_year": "From business.prev_yr_total_gross_sales.",
    "lines_of_business_1":   "Split business.business_nature by comma, first item.",
    "lines_of_business_2":   "Split business.business_nature by comma, second item.",
    "lines_of_business_3":   "Split business.business_nature by comma, third item.",
    "lines_of_business_4":   "Split business.business_nature by comma, fourth item.",
    "lines_of_business_5":   "Split business.business_nature by comma, fifth item.",
    "requestor_full_name":   "From subject_view(header,line)['full_name'] or person(first_name,last_name).",
    "requestor_addr":        "From subject_view(header,line)['address'] or person address.",
    "doc_purpose":           "From line.purpose_code/label or details.purpose_code.",
    "or_number":             "From payments.latest_or_number or header.or_number.",
    "paid_amount":           "From payments.latest_amount or payments.amount.",
    "paid_date":             "From payments.latest_paid_at or payments.paid_at (or payments.latest_or_time).",
    "numbersixteen":         "Punong Barangay name, e.g. settings.BRGY_CAPTAIN_NAME or header.captain_name.",
    "numberfour":            "Application/Request No. Use header.request_code (fallback: doc_request_id).",
    "numberfour=":           "Same as numberfour; normalize to header.request_code.",
    "numberfive":            "Date Applied. Use header.created_at/created_ts/date_created (format to text).",
    "year_issued":           "Current year or from issue date.",
}

# ────────────────────────────────────────────────────────────
# SECTION: Date helpers (NEW)
# ────────────────────────────────────────────────────────────
def _parse_dt_any(val: Any) -> Optional[datetime]:
    """Accept datetime/date/iso string and return a datetime (UTC-aware if possible)."""
    try:
        if isinstance(val, datetime):
            return val
        if isinstance(val, dt.date) and not isinstance(val, datetime):
            return datetime(val.year, val.month, val.day, tzinfo=timezone.get_current_timezone())
        if isinstance(val, str):
            s = val.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(s)
            except Exception:
                # try plain date
                try:
                    d = dt.date.fromisoformat(s[:10])
                    return datetime(d.year, d.month, d.day, tzinfo=timezone.get_current_timezone())
                except Exception:
                    return None
    except Exception:
        return None
    return None

def _friendly_date_text(val: Any) -> Optional[str]:
    """Return 'September 27, 2025' for provided datetime-like value; None if cannot parse."""
    d = _parse_dt_any(val)
    if not d:
        return None
    try:
        # use local time if aware; otherwise leave as is
        try:
            d_local = timezone.localtime(d)
        except Exception:
            d_local = d
        return d_local.strftime("%B %d, %Y")
    except Exception:
        return None

# ────────────────────────────────────────────────────────────
# SECTION: Email helpers
# ────────────────────────────────────────────────────────────
def _resolve_person_id_from_header(header: Dict[str, Any]) -> Optional[int]:
    """Find the most appropriate person_id in the header payload."""
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
    person_id = _resolve_person_id_from_header(header)
    print(f"[EMAIL DEBUG] resolved person_id from header -> {person_id!r}")
    full_name, email = _lookup_person_contact(person_id)
    if not email:
        print("[EMAIL DEBUG] no email found on file; skipping send.")
        return False, "No email on file for this resident. Notification not sent."

    req_code = header.get("request_code") or f"REQ-{header.get('doc_request_id','')}"
    doc_names = [ (l.get("document_type_name") or "").strip() for l in (lines or []) ]
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

    _debug_email_preview(subject, to_list, body_txt, body_html)

    try:
        result = send_email(
            subject=subject,
            to=to_list,
            body_text=body_txt,
            body_html=body_html,
            from_name=barangay_name,
            fail_silently=False,
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
        print(f"[EMAIL DEBUG] lookup person_id={person_id} -> full_name={full!r}, email={email!r}")
        return full, email
    except Exception as e:
        logger.exception("Lookup failed for person_id=%s", person_id)
        print(f"[EMAIL DEBUG] lookup failed for person_id={person_id}: {e}")
        return None, None




# ────────────────────────────────────────────────────────────
# SECTION: Doc-type cache helper
# ────────────────────────────────────────────────────────────
_DOC_TYPES_ALL_CACHE: List[str] = []

def _fetch_purposes_by_request_type(req_doc_type_id: int) -> List[Dict[str, Any]]:
    q = (
        supabase.table("document_purpose")
        .select(
            "document_purpose_id, request_document_type_id, purpose_code, purpose_label, "
            "default_details, default_offense_no, business_category_id, "  # ← NEW
            "fee_item:fee_item_id(fee_item_id, current_amount, "
            "exempt_ftj, exempt_senior, exempt_pwd, exempt_indigent, exempt_student)"
        )
        .eq("request_document_type_id", req_doc_type_id)
        .order("purpose_label")
    ).execute()

    rows = q.data or []
    out = []
    for r in rows:
        fi = r.get("fee_item") or {}
        out.append({
            "document_purpose_id": r["document_purpose_id"],
            "purpose_label": r.get("purpose_label"),
            "purpose_code": r.get("purpose_code"),
            "business_category_id": r.get("business_category_id"),  # ← NEW
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
    
def _fetch_doc_types_all() -> List[str]:
    """Get the full list of document type names for the filter panel."""
    global _DOC_TYPES_ALL_CACHE
    if _DOC_TYPES_ALL_CACHE:
        return _DOC_TYPES_ALL_CACHE
    try:
        res = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .order("request_document_type_name")
            .execute()
        )
        names = [
            (r.get("request_document_type_name") or "").strip()
            for r in (res.data or [])
            if (r.get("request_document_type_name") or "").strip()
        ]
        _DOC_TYPES_ALL_CACHE = names
        return names
    except Exception as e:
        logger.warning("Failed to fetch doc types list: %s", e)
        return []

# ────────────────────────────────────────────────────────────
# SECTION: Clerk Queue + Detail screens
# ────────────────────────────────────────────────────────────
@session_login_required
@role_required(CLERK_ROLE)
@nocache
def queue(request: HttpRequest):
    q = (request.GET.get("q") or "").strip() or None

    # status filter
    statuses = request.GET.getlist("status")
    if not statuses:
        raw = (request.GET.get("status") or "").strip()
        statuses = [s for s in raw.split(",") if s] if raw else CLERK_STATUSES_ALL[:2]

    # doc-type filter
    doc_types = request.GET.getlist("doc_type")
    if not doc_types:
        raw_dt = (request.GET.get("doc_type") or "").strip()
        doc_types = [s for s in raw_dt.split(",") if s]

    # base query
    query = (
        supabase.table("v_doc_request_list_ex")
        .select("*")
        .order("doc_request_id", desc=True)
    )
    if statuses:
        query = query.in_("status", statuses)
    if q:
        array_probe = "{" + q + "}"
        query = query.or_(
            f"request_code.ilike.%{q}%,doc_types.ov.{array_probe},purposes.ov.{array_probe}"
        )

    res = query.limit(200).execute()
    rows: List[Dict[str, Any]] = res.data or []

    # in-memory filter for selected doc types
    if doc_types:
        selected = {str(d).strip().lower() for d in doc_types}
        def _overlaps(row: Dict[str, Any]) -> bool:
            vals = row.get("doc_types") or []
            have = {str(v).strip().lower() for v in vals if v}
            return bool(have & selected)
        rows = [r for r in rows if _overlaps(r)]

    # UI adornments
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

    # list of doc types for filter panel
    doc_types_all = _fetch_doc_types_all()
    if not doc_types_all:
        seen: set[str] = set()
        for r in rows:
            for name in (r.get("doc_types") or []):
                name = (name or "").strip()
                if name:
                    seen.add(name)
        doc_types_all = sorted(seen)

    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "clerk/queue.html", {
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "q": q or "",
        "statuses": statuses,
        "statuses_all": CLERK_STATUSES_ALL,
        "doc_types": doc_types,
        "doc_types_all": doc_types_all,
        "active_count": len(statuses) + len(doc_types),
    })


from datetime import datetime
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.utils.dateparse import parse_datetime

PH_TZ = ZoneInfo("Asia/Manila")

def _fmt_occured_at(val) -> str:
    """Accepts a datetime or ISO string, returns a Manila-local formatted string."""
    if not val:
        return "—"
    dt = None
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, str):
        dt = parse_datetime(val)  # handles '...+00:00' etc.
    if not dt:
        return val  # show raw if parsing fails
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    # convert to Asia/Manila
    dt_local = timezone.localtime(dt, PH_TZ)
    return dt_local.strftime("%b %d, %Y • %I:%M %p")


def _resolve_actor_name(ev: dict, header: dict) -> str:
    """Return a friendly actor name for a timeline event."""
    # Prefer explicit names on the event
    for k in ("staff_name", "resident_name"):
        v = (ev.get(k) or "").strip()
        if v:
            return v

    actor = (ev.get("actor") or "").strip()
    if actor:
        # If it's an ID like "4", show the requester's name instead
        if actor.isdigit() and header.get("requester_full_name"):
            return header["requester_full_name"]
        return actor

    # Fallbacks by user type
    ut = (ev.get("user_type_name") or "").strip().upper()
    if ut == "PERSON" and header.get("requester_full_name"):
        return header["requester_full_name"]

    return "SYSTEM"

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def detail(request: HttpRequest, doc_request_id: int):
    # small local normalizer so we can compare values robustly
    def _norm(s) -> str:
        return re.sub(r"[\s_]+", "_", str(s or "").strip().upper())

    try:
        data: Dict[str, Any] = _fetch_bundle(doc_request_id)
    except APIError as e:
        messages.error(request, f"Supabase error: {escape(getattr(e, 'message', str(e)))}")
        return redirect("clerk:queue")

    header = data.get("header", {}) or {}
    lines = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline = data.get("timeline", []) or []

    # Authorization Letter assets (images / pdfs)
    auth_links = build_auth_links(settings, header, lines)

    # Status chip UI
    ui = STATUS_UI.get(header.get("status")) or {
        "label": header.get("status") or "—",
        "cls": "badge text-bg-secondary"
    }

    # Enrich line items for display
    for l in lines:
        details = l.get("details") or {}
        # humanized purpose (fallback to details.purpose_code)
        l["purpose_display"] = titleize(l.get("purpose_code") or details.get("purpose_code"))
        # show applied waiver reasons as chips
        l["reason_chips"] = list(l.get("reasons_applied") or details.get("reason_tags") or [])
        # flag for full exemption (or explicit boolean if your backend sets it)
        l["is_exempt"] = bool(
            l.get("is_exempt")
            or (
                (l.get("waived_amount") or 0) > 0
                and (l.get("base_amount") or 0) <= (l.get("waived_amount") or 0)
            )
        )

    # OR number and receipt-ish fields exposed to UI/PDFs
    header["or_number"] = (
        payments.get("latest_or_number")
        or header.get("latest_or_number")
        or header.get("or_number")
        or ""
    )
    header["paid_amount"] = payments.get("latest_amount") or payments.get("amount")
    header["paid_date"]   = payments.get("latest_paid_at") or payments.get("paid_at") or payments.get("latest_or_time")

    # Subject display fields
    subj = subject_view(header, {})
    header["is_on_behalf"] = subj["is_on_behalf"]
    header["subject_full_name"] = subj["full_name"]
    header["subject_address"] = subj["address"]
    header["subject_age"] = subj["age"]
    header["subject_civil_status"] = subj["civil_status"]
    header["subject_nationality"] = subj["nationality"]

    # --- CTC context for UI banner & modal (if any) ---
    ctc_mode = False
    ctc_of = None
    ctc_ref_request_id = None
    ctc_ref_code = None
    try:
        for l in lines:
            if (l.get("document_type_name") or "").strip().upper() == "CERTIFIED TRUE COPY":
                ctc_mode = True
                det = l.get("details") or {}
                ctc_of = (det.get("ctc_of") or "").strip() or None
                ctc_ref_request_id = det.get("reference_request_id")
                break
        if ctc_mode and ctc_ref_request_id:
            ref_bundle = _fetch_bundle(int(ctc_ref_request_id))
            ref_header = ref_bundle.get("header") or {}
            ctc_ref_code = ref_header.get("request_code")
    except Exception:
        pass

    # Timestamps formatted for Asia/Manila
    header["created_fmt"] = _fmt_occured_at(header.get("created_at"))

    for ev in timeline:
        ev["occur_fmt"] = _fmt_occured_at(
            ev.get("occurred_at") or ev.get("occurredAt") or ev.get("occur_time")
        )
        ev["display_actor"] = _resolve_actor_name(ev, header)

    # === NEW: detect "paid" purely from status/timeline ===
    was_marked_paid = False
    if _norm(header.get("status")) == "PAID":
        was_marked_paid = True
    else:
        for ev in timeline:
            act = _norm(ev.get("action"))
            to_status = _norm(ev.get("to_status"))
            if (act == "STATUS_CHANGED" and to_status == "PAID") or act == "PAYMENT_ACCEPTED":
                was_marked_paid = True
                break

    return render(request, "clerk/detail.html", {
        "header": header,
        "status_ui": ui,
        "lines": lines,
        "payments": payments,
        "timeline": timeline,
        "ctc_mode": ctc_mode,
        "ctc_of": ctc_of,
        "ctc_ref_request_id": ctc_ref_request_id,
        "ctc_ref_code": ctc_ref_code,
        "auth_links": auth_links,
        "was_marked_paid": was_marked_paid,  # <-- used by the template
    })

# ────────────────────────────────────────────────────────────
# SECTION: Status change actions
# ────────────────────────────────────────────────────────────
@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def mark_request_ready_for_pickup(request: HttpRequest, doc_request_id: int):
    print(f"[EMAIL DEBUG] mark_request_ready_for_pickup called for doc_request_id={doc_request_id}")
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

# ────────────────────────────────────────────────────────────
# SECTION: Printing helpers (Business Clearance mapping)
# ────────────────────────────────────────────────────────────
def _apply_pdf_field_mapping(
    doc_name: str,
    field_names: List[str],
    values: Dict[str, Any],
    include_debug: bool=False
) -> Dict[str, Any]:
    """
    Map semantic → PDF field names for Business Clearance with
    logging + advice on how to fetch missing data.
    """
    nm = (doc_name or "").strip().upper()
    if nm == BRGY_BUSINESS_DOC_NAME:
        # Advice per semantic key (for helpful logs)
        advice = {
          "applicant_nationality": "Join person.nationality_id → nationality.nationality_name.",
          "applicant_full_name":   "From person(first_name,last_name) of subject/requester.",
          "applicant_age":         "Compute from person.birthdate.",
          "business_name_style":   "From business.business_name.",
          "business_address":      "From business.address_id → address(street,purok_sitio,barangay,city).",
          "capital_invested":      "From business.capital_invested.",
          "gross_sales_prev_year": "From business.prev_yr_total_gross_sales.",
          "lines_of_business_1":   "Split business.business_nature by comma (1st).",
          "lines_of_business_2":   "Split business.business_nature by comma (2nd).",
          "lines_of_business_3":   "Split business.business_nature by comma (3rd).",
          "lines_of_business_4":   "Split business.business_nature by comma (4th).",
          "lines_of_business_5":   "Split business.business_nature by comma (5th).",
          "paid_amount":           "From payments.latest_amount or payments.amount.",
        }
        mapped: Dict[str, Any] = {}
        for skey, pdf_field in BUSINESS_CLEARANCE_FIELD_MAP.items():
            if pdf_field not in field_names:
                continue
            val = values.get(skey)
            if val is None or str(val).strip() == "":
                # label field name when missing to aid discovery
                if include_debug:
                    mapped.setdefault(pdf_field, pdf_field)
                print(f"[PRINT MAP] {nm}: {skey} → {pdf_field} = {pdf_field!r} [MISSING→printing field name]")
                if skey in advice:
                    print(f"[PRINT ADVICE] Missing '{skey}'. How to get it: {advice[skey]}")
            else:
                mapped[pdf_field] = val
                print(f"[PRINT MAP] {nm}: {skey} → {pdf_field} = {val!r}")
        return mapped

    # Non-business-clearance: return only matching keys as-is
    return {fn: values.get(fn) for fn in field_names}

# ────────────────────────────────────────────────────────────
# SECTION: Printing action
# ────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────
# SECTION: Printing action
# ────────────────────────────────────────────────────────────
@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def mark_for_printing(request: HttpRequest, doc_request_id: int):
    include_debug = (request.POST.get("debug") == "1")

    def _override_if_blank(d: Dict[str, Any], key: str, fallback: Any):
        cur = d.get(key)
        cur_blank = (cur is None) or (str(cur).strip() == "")
        if cur_blank and fallback is not None and str(fallback).strip() != "":
            d[key] = fallback

    # ---- Load the primary (this CTC) bundle
    try:
        data_raw = _fetch_bundle(doc_request_id)
        data = (data_raw[0] if isinstance(data_raw, list) and data_raw else data_raw) or {}
    except APIError as e:
        messages.error(request, f"Supabase error: {escape(getattr(e, 'message', str(e)))}")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    header: Dict[str, Any]   = data.get("header", {}) or {}
    lines: List[Dict[str,Any]] = data.get("lines", []) or []
    payments: Dict[str, Any] = data.get("payments", {}) or {}

    # Expose receipt info to PDFs (from THIS request – the CTC usually has the OR)
    line_total = sum(float(l.get("line_total", 0) or 0) for l in lines)
    header["or_number"]   = payments.get("latest_or_number") or payments.get("or_number") or _safe_str(header.get("or_number"))
    header["paid_amount"] = line_total or payments.get("amount")
    header["paid_date"]   = payments.get("latest_paid_at") or payments.get("paid_at") or payments.get("latest_or_time")

    print("[PRINT DEBUG] header snapshot:", json.dumps({
        "request_code": header.get("request_code"),
        "or_number": header.get("or_number"),
        "paid_amount": header.get("paid_amount"),
        "paid_date": str(header.get("paid_date")),
    }, indent=2, default=str))

    outputs: List[tuple[str, bytes]] = []
    debug_items: List[Dict[str, Any]] = []
    base_dir = _pdf_templates_dir()

    for idx, line in enumerate(lines, start=1):
        original_doc_name = _safe_str(line.get("document_type_name") or f"doc-{idx}")
        is_ctc = (original_doc_name.strip().upper() == "CERTIFIED TRUE COPY")

        # ---------- If CTC, load the ORIGINAL request it's certifying ----------
        ref_header: Dict[str, Any] = {}
        ref_line: Dict[str, Any]   = {}
        ref_payments: Dict[str, Any] = {}
        if is_ctc:
            det = (line.get("details") or {})
            ctc_of = (det.get("ctc_of") or "").strip().upper() or None
            ref_id = det.get("reference_request_id") or det.get("reference_doc_request_id")
            try:
                if ref_id:
                    rb_raw = _fetch_bundle(int(ref_id))
                    rb = (rb_raw[0] if isinstance(rb_raw, list) and rb_raw else rb_raw) or {}
                    ref_header   = rb.get("header", {}) or {}
                    ref_lines    = rb.get("lines", []) or []
                    ref_payments = rb.get("payments", {}) or {}
                    # choose the referenced line (same doc) or first
                    for rl in ref_lines:
                        if ctc_of and (str(rl.get("document_type_name") or "").strip().upper() == ctc_of):
                            ref_line = rl
                            break
                    if not ref_line and ref_lines:
                        ref_line = ref_lines[0]
            except Exception as e:
                print(f"[CTC DEBUG] Could not load reference bundle for CTC: {e}")

        # The document to PRINT (for CTC we print the original's document)
        doc_name_print = _safe_str(ref_line.get("document_type_name")) if (is_ctc and ref_line) else original_doc_name
        doc_name_upper = doc_name_print.strip().upper()

        # The document to PRINT (for CTC we print the original's document)
        doc_name_print = _safe_str(ref_line.get("document_type_name")) if (is_ctc and ref_line) else original_doc_name
        doc_name_upper = doc_name_print.strip().upper()

        # Is this a (CTC of) Barangay Business Clearance?
        is_bc = (
            doc_name_upper == BRGY_BUSINESS_DOC_NAME
            or (is_ctc and ((line.get("details") or {}).get("ctc_of","").strip().upper() == BRGY_BUSINESS_DOC_NAME))
        )

        # ✅ DEFAULT template (works for all other docs)
        template_file = _choose_template(doc_name_print, False)

        # Template selection
        if is_bc:
            if is_ctc:
                template_file = CTC_BRGY_BUSINESS_PDF_FILE
            else:
                template_file = BRGY_BUSINESS_PDF_FILE

        # (Optional) still honor a manual per-line override if you use it
        if (line.get("details") or {}).get("template_override"):
            template_file = (line["details"]["template_override"])
            
        template_path = os.path.join(base_dir, template_file)
        print(f"[PRINT DEBUG] doc='{doc_name_print}' (from='{original_doc_name}') -> template='{template_file}' (CTC={is_ctc})")

        if not os.path.exists(template_path):
            alt = os.path.join(settings.BASE_DIR, "clerk", "pdf_templates", template_file)
            if os.path.exists(alt):
                template_path = alt
            else:
                print(json.dumps({
                    "doc_index": idx, "doc_name": doc_name_print, "template_file": template_file,
                    "template_path": template_path, "exists": False, "reason": "Template not found"
                }, indent=2))
                continue

        # ---------- Build values ----------
        if is_ctc and ref_header and ref_line:
            base_values   = _fill_fields_for_line(ref_header, ref_line)
            detail_values = (ref_line.get("details") or {})
            combined_values = {**detail_values, **base_values}
            # Helpful CTC stamps (if any template uses them)
            combined_values["is_ctc"] = True
            combined_values["ctc_reference_code"] = ref_header.get("request_code")
            ref_created = ref_header.get("created_at") or ref_header.get("created_ts") or ref_header.get("date_created")
            combined_values["ctc_reference_date"] = _friendly_date_text(ref_created) or _safe_str(ref_created)

            # If original has blanks, override from **this CTC's** header/payments
            _override_if_blank(combined_values, "or_number", header.get("or_number") or payments.get("latest_or_number"))
            _override_if_blank(combined_values, "paid_amount", header.get("paid_amount") or payments.get("latest_amount"))
            _override_if_blank(combined_values, "paid_date", _friendly_date_text(header.get("paid_date") or payments.get("latest_or_time")))
        else:
            base_values   = _fill_fields_for_line(header, line)
            detail_values = (line.get("details") or {})
            combined_values = {**detail_values, **base_values}
            _override_if_blank(combined_values, "or_number", header.get("or_number") or payments.get("latest_or_number"))
            _override_if_blank(combined_values, "paid_amount", header.get("paid_amount") or payments.get("latest_amount"))
            _override_if_blank(combined_values, "paid_date", _friendly_date_text(header.get("paid_date") or payments.get("latest_or_time")))

        # Subject fallbacks
        try:
            _subj = subject_view(ref_header if (is_ctc and ref_header) else header,
                                 ref_line   if (is_ctc and ref_line)   else line)
            combined_values.setdefault("applicant_full_name", _safe_str(_subj.get("full_name")))
            combined_values.setdefault("applicant_age", _safe_str(_subj.get("age")))
            combined_values.setdefault("applicant_nationality", _safe_str(_subj.get("nationality")))
        except Exception as e:
            print(f"[PRINT DEBUG] subject fallbacks failed: {e}")

        # BC meta boxes (request code/date from the bundle we’re printing)
        use_header = ref_header if (is_ctc and ref_header) else header
        created_any = use_header.get("created_at") or use_header.get("created_ts") or use_header.get("date_created")
        combined_values["numberfour"]  = use_header.get("request_code")
        combined_values["numberfive"]  = _friendly_date_text(created_any) or _safe_str(created_any)
        combined_values.setdefault("numbersixteen", use_header.get("captain_name") or "Lourdes R. Ramirez")
        combined_values.setdefault("year_issued", timezone.localtime().strftime("%Y"))

        # Enrich Business Clearance fields if needed
        if is_bc:
            bc_keys = ["business_name_style","business_address","capital_invested","gross_sales_prev_year"]
            if any(not _safe_str(combined_values.get(k)).strip() for k in bc_keys):
                bid = use_header.get("business_id")
                if not bid:
                    try:
                        r = (supabase.table("document_request")
                             .select("business_id").eq("doc_request_id", doc_request_id)
                             .limit(1).execute())
                        bid = ((r.data or [{}])[0] or {}).get("business_id")
                    except Exception as e:
                        print(f"[PRINT DEBUG] could not fetch business_id for request {doc_request_id}: {e}")
                subj_pid = use_header.get("subject_person_id") or use_header.get("requested_by_person_id")
                if bid:
                    try:
                        bc_enrich = _fetch_business_clearance_fields(int(bid), int(subj_pid) if subj_pid else None)
                        combined_values = {**bc_enrich, **combined_values}
                    except Exception as e:
                        print(f"[PRINT DEBUG] business fallback failed: {e}")

        # ---------- Map & fill PDF ----------
        field_names = _get_all_pdf_field_names(template_path)
        # IMPORTANT: if this is (CTC of) Business Clearance, use the BC mapping name
        mapping_doc_name = BRGY_BUSINESS_DOC_NAME if is_bc else doc_name_print
        values_mapped = _apply_pdf_field_mapping(mapping_doc_name, field_names, combined_values, include_debug)

        merged = {name: (values_mapped.get(name) if str(values_mapped.get(name) or "").strip() else "No data")
                  for name in field_names}

        try:
            pdf_bytes = _fill_pdf_with_values(template_path, merged)
        except Exception:
            with open(template_path, "rb") as f:
                pdf_bytes = f.read()

        # Output filename (add ctc-of-… when applicable)
        safe_name = doc_name_print.lower().replace(" ", "-")
        out_name = (f"{header.get('request_code','REQ')}-ctc-of-{safe_name}.pdf"
                    if is_ctc else f"{header.get('request_code','REQ')}-{safe_name}.pdf")
        outputs.append((out_name, pdf_bytes))
        debug_items.append({
            "output_filename": out_name,
            "doc_name": doc_name_print,
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
        for fname, b in outputs: zf.writestr(fname, b)
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
    resp["Content-Disposition"] = f'attachment; filename="{req_code}-documents.zip'
    return resp


# ────────────────────────────────────────────────────────────
# SECTION: Release / Decline
# ────────────────────────────────────────────────────────────
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
    print("\n" + "="*72)
    print("[DECLINE DEBUG] called")
    reason = (request.POST.get("reason") or "").strip() or None
    staff_id = _staff_id(request)

    print(f"[DECLINE DEBUG] doc_request_id = {doc_request_id}")
    print(f"[DECLINE DEBUG] staff_id       = {staff_id}")
    print(f"[DECLINE DEBUG] reason         = {reason!r}")

    # Load bundle first so we can inspect status/timeline/payments
    try:
        bundle = _fetch_bundle(doc_request_id)
    except APIError as e:
        messages.error(request, f"Unable to load request: {escape(getattr(e,'message', str(e)))}")
        print("[DECLINE DEBUG] ERROR: _fetch_bundle failed:", e)
        print("="*72 + "\n")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    header    = (bundle or {}).get("header", {}) or {}
    payments  = (bundle or {}).get("payments", {}) or {}
    timeline  = (bundle or {}).get("timeline", []) or []

    # Snapshot for logs
    print(f"[DECLINE DEBUG] header.request_code     = {header.get('request_code')}")
    print(f"[DECLINE DEBUG] header.status           = {header.get('status')}")
    print(f"[DECLINE DEBUG] header.or_number        = {header.get('or_number')}")
    print(f"[DECLINE DEBUG] payments.total_paid     = {float(payments.get('total_paid') or 0)}")
    print(f"[DECLINE DEBUG] header.amount_due       = {float(header.get('amount_due') or 0)}")

    # Determine paid-ness (now also looks at status/timeline)
    def _norm(s): return re.sub(r"[\s_]+", "_", str(s or "").strip().upper())
    status_now = _norm(header.get("status"))
    has_or     = bool(header.get("or_number"))
    total_paid = float(payments.get("total_paid") or 0)

    timeline_paid = False
    for ev in (timeline or []):
        act = _norm(ev.get("action"))
        to_status = _norm(ev.get("to_status"))
        if act == "PAYMENT_ACCEPTED" or (act == "STATUS_CHANGED" and to_status == "PAID"):
            timeline_paid = True
            break

    is_paid = (status_now == "PAID") or timeline_paid or (total_paid > 0) or has_or
    print(f"[DECLINE DEBUG] is_paid?                = {is_paid}")
    if timeline_paid:
        print("[DECLINE DEBUG] timeline shows a payment event (PAYMENT_ACCEPTED/→PAID).")

    # Path A: NOT paid → simple decline
    if not is_paid:
        print("[DECLINE DEBUG] PATH: simple decline (no refund)")
        print(f"[DECLINE DEBUG] CALL: _set_status(doc_request_id={doc_request_id}, status='DECLINED', staff_id={staff_id}, reason={reason!r})")
        err = _set_status(doc_request_id, "DECLINED", staff_id, reason)
        print(f"[DECLINE DEBUG] RESULT: err = {err!r}")
        print("="*72 + "\n")
        if err:
            messages.error(request, f"Failed: {escape(err)}")
        else:
            messages.success(request, "Request declined.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    # Path B: PAID → decline + open refund ticket (amount NULL lets SQL compute)
    print("[DECLINE DEBUG] PATH: decline with REFUND ticket")
    try:
        from .services.requests_service import decline_and_request_refund
    except Exception as e:
        print("[DECLINE DEBUG] import decline_and_request_refund failed:", e)
        messages.error(request, "Server error (refund handler missing).")
        print("="*72 + "\n")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    print(f"[DECLINE DEBUG] CALL: decline_and_request_refund(doc_request_id={doc_request_id}, staff_id={staff_id}, reason={reason!r}, refund_amount=None)")
    err, refund_id = decline_and_request_refund(doc_request_id, int(staff_id), reason, refund_amount=None)
    print(f"[DECLINE DEBUG] RESULT: err={err!r}, refund_id={refund_id!r}")
    print("="*72 + "\n")

    if err:
        messages.error(request, f"Decline failed: {escape(err)}")
    else:
        msg = "Request declined. Refund ticket created and sent for Treasurer processing."
        if refund_id:
            msg = f"Request declined. Refund ticket #{refund_id} created and sent for Treasurer processing."
        messages.success(request, msg)
    return redirect("clerk:detail", doc_request_id=doc_request_id)

# ────────────────────────────────────────────────────────────
# SECTION: Identity verification screens
# ────────────────────────────────────────────────────────────
STATUS_APPROVED = 3
STATUS_REJECTED = 4
STATUS_DECLINE  = 7

@session_login_required
@role_required(CLERK_ROLE)
@nocache
@inject
def dashboard(
    request: HttpRequest,
    clerk_dashboard_service=Provide[AppContainer.clerk_dashboard_service],
):
    user_role = _auth_role_name(request)

    kpis = {
        "doc_requests": 0,
        "doc_requests_delta": None,
        "pending_verifications": 0,
        "verif_delta": None,
        "active_businesses": 0,
        "new_businesses_week": None,
        "residents_total": 0,
        "new_residents_month": None,
    }

    dashboard_json = None

    try:
        payload = clerk_dashboard_service.get_dashboard_content() or {}
        kpis = payload.get("kpis", kpis)
        dashboard_json = payload.get("dashboard_json")
    except Exception as exc:
        print("Error fetching clerk dashboard KPIs:", exc)

    return render(request, "clerk/dashboard.html", {
        'page_path' : f'{user_role} / Dashboard',
        'page_title' : 'Dashboard',
        'kpis': kpis,
        'dashboard_json': dashboard_json,
        'today': datetime.now().strftime("%B %d, %Y"),
    })

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def review_approve(request: HttpRequest):
    """List of ID verification requests."""
    profile = getattr(request, "person_profile", None)

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
        dt_ = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
        person["submitted_fmt"] = timezone.localtime(dt_).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        person["submitted_fmt"] = raw_dt or "—"

    gps = person.get("government_programs")
    if isinstance(gps, str):
        gps = [s.strip() for s in gps.split(",") if s.strip()]
    person["government_programs"] = gps or []

    # Combine front and back ID files
    front_files = person.get("valid_id_front_files") or []
    back_files = person.get("valid_id_back_files") or []
    person["valid_id_files"] = front_files + back_files
    person["selfie_file"] = person.get("selfie_file") or None
    
    print(f"TEMPLATE DEBUG - Front files: {front_files}")
    print(f"TEMPLATE DEBUG - Back files: {back_files}")
    print(f"TEMPLATE DEBUG - Combined: {person['valid_id_files']}")
    print(f"TEMPLATE DEBUG - Selfie: {person['selfie_file']}")
    print(f"TEMPLATE DEBUG - Person ID: {req_id}")
    print(f"TEMPLATE DEBUG - Raw person data keys: {list(person.keys())}")

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
        person["latest_status"]  = status_row.get("status_text") or person.get("latest_status") or "Pending"
        person["remarks"]        = status_row.get("latest_remarks") or person.get("remarks")

    return render(request, "clerk/resident/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "person": person,
    })

# ────────────────────────────────────────────────────────────
# SECTION: AJAX helpers (search and purposes)
# ────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────
# SECTION: AJAX helpers (search and purposes)
# ────────────────────────────────────────────────────────────
@session_login_required
@role_required(CLERK_ROLE)
@nocache
def ajax_owner_businesses(request: HttpRequest) -> HttpResponse:
    """
    Return <option> list of the selected owner's businesses.
    Used when Document Type is 'Barangay Business Clearance' or 'Certified True Copy' (CTC).

    GET:
      owner_person_id          (int, required)
      require_has_clearance    ('1'|'true' to show ONLY businesses that already have a clearance)
    """
    try:
        owner_person_id = int(request.GET.get("owner_person_id") or 0)
    except Exception:
        owner_person_id = 0

    if not owner_person_id:
        html = '<option value="">— select resident first —</option>'
        return HttpResponse(html)

    require_has_clearance = str(request.GET.get("require_has_clearance") or "").lower() in ("1", "true", "yes")

    try:
        q = (
            supabase.table("business")
            .select(
                "business_id, business_name, business_category_id, has_business_clearance, "
                "address:address_id(street, barangay, city)"
            )
            .eq("business_owner_id", owner_person_id)
        )
        if require_has_clearance:
            q = q.eq("has_business_clearance", True)

        resp = q.order("business_name").execute()
        rows = resp.data or []
    except Exception as e:
        rows = []
        logger.warning("ajax_owner_businesses failed: %s", e)

    html = render_to_string("clerk/doc_req/_business_options.html", {"businesses": rows})
    return HttpResponse(html)


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

# ────────────────────────────────────────────────────────────
# SECTION: Walk-in Document Request (with BC enrichment)
# ────────────────────────────────────────────────────────────
def _fetch_request_doc_types() -> List[Dict[str, Any]]:
    """Mirror of mobile getDocumentTypes()."""
    res = (
        supabase.table("request_document_type")
        .select("request_document_type_id, request_document_type_name")
        .order("request_document_type_name")
        .execute()
    )
    return res.data or []

def _fetch_purposes_by_request_type(req_doc_type_id: int) -> List[Dict[str, Any]]:
    """Mirror of mobile getPurposesByDocumentType(), plus fee flags/amount."""
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
    doc_types = _fetch_request_doc_types()

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



# ────────────────────────────────────────────────────────────
# SECTION: Business Clearance field derivation
# ────────────────────────────────────────────────────────────
def _age_from_birthdate(bd: Optional[str | dt.date]) -> Optional[int]:
    try:
        if not bd:
            return None
        if isinstance(bd, str):
            bd = dt.date.fromisoformat(bd)
        today = dt.date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None

def _fetch_business_clearance_fields(business_id: int, subject_person_id: Optional[int]) -> Dict[str, Any]:
    """
    Pull business + address + subject basics and return the semantic keys
    that the Business Clearance PDF expects (before mapping).

    CHANGE: First line of business now comes from business_category_id ->
    document_purpose.purpose_label (falls back to business_nature).
    """
    # Business core + address (+ category id)
    try:
        bq = (
            supabase.table("business")
            .select(
                "business_name, business_nature, business_category_id, "
                "capital_invested, prev_yr_total_gross_sales, "
                "address:address_id(street, barangay, city, purok_sitio:purok_sitio_id(purok_sitio_name))"
            )
            .eq("business_id", business_id)
            .limit(1)
            .execute()
        )
        b = (bq.data or [None])[0] or {}
    except Exception as e:
        print(f"[WALKIN DEBUG] fetch business failed: {e}")
        b = {}

    # Subject/applicant info
    subj: Dict[str, Any] = {}
    if subject_person_id:
        try:
            pq = (
                supabase.table("person")
                .select("first_name,last_name,birthdate, nationality:nationality_id(nationality_name)")
                .eq("person_id", subject_person_id)
                .limit(1)
                .execute()
            )
            pr = (pq.data or [None])[0] or {}
            full = f"{(pr.get('first_name') or '').strip()} {(pr.get('last_name') or '').strip()}".strip()
            subj = {
                "applicant_full_name": full or None,
                "applicant_age": _age_from_birthdate(pr.get("birthdate")),
                "applicant_nationality": (((pr.get("nationality") or {}) or {}).get("nationality_name")) or None
            }
        except Exception as e:
            print(f"[WALKIN DEBUG] fetch subject failed: {e}")

    # Address compose
    addr = b.get("address") or {}
    purok = (((addr.get("purok_sitio") or {}) or {}).get("purok_sitio_name")) or ""
    parts = [addr.get("street"), purok, addr.get("barangay"), addr.get("city")]
    business_address = ", ".join([str(p).strip() for p in parts if p])

    # ---- NEW: category label via business_category_id -> document_purpose.purpose_label
    category_label: Optional[str] = None
    cat_id = b.get("business_category_id")
    if cat_id:
        try:
            dpq = (
                supabase.table("document_purpose")
                .select("purpose_label")              # optionally also select request_document_type_id if you want to guard it (e.g., = 4)
                .eq("document_purpose_id", int(cat_id))
                .limit(1)
                .execute()
            )
            category_label = ((dpq.data or [{}])[0] or {}).get("purpose_label")
        except Exception as e:
            print(f"[WALKIN DEBUG] fetch category label failed: {e}")

    # Lines of business:
    # 1) Prefer the category label for slot #1
    # 2) Then append any comma-separated items from business_nature
    nature = (b.get("business_nature") or "").strip()
    extra = [s.strip() for s in nature.split(",") if s.strip()]
    lob: List[str] = []
    if category_label:
        lob.append(category_label)
        # avoid duplicate if the same text appears in business_nature
        extra = [x for x in extra if x.lower() != category_label.lower()]
    lob.extend(extra)
    while len(lob) < 5:
        lob.append("")

    details = {
        **subj,
        "business_name_style": b.get("business_name"),
        "business_address": business_address or None,
        "capital_invested": b.get("capital_invested"),
        "gross_sales_prev_year": b.get("prev_yr_total_gross_sales"),
        "lines_of_business_1": lob[0] if lob else None,
        "lines_of_business_2": lob[1] if lob else None,
        "lines_of_business_3": lob[2] if lob else None,
        "lines_of_business_4": lob[3] if lob else None,
        "lines_of_business_5": lob[4] if lob else None,
        # Hint the printing stage to use the correct PDF
        "template_override": BRGY_BUSINESS_PDF_FILE,
    }
    print("[WALKIN DEBUG] derived Business Clearance details:", json.dumps(details, indent=2, default=str))
    print("[WALKIN DEBUG] raw business row:", json.dumps(b, indent=2, default=str))
    return details


# ────────────────────────────────────────────────────────────
# SECTION: Walk-in create (payload builder + BC enrichment)
# ────────────────────────────────────────────────────────────

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def walkin_create(request: HttpRequest):
    """POST handler that builds the same payload the mobile sends, but routes through
    create_document_request_walkin so we tag channel=WALKIN and filed_by clerk staff.
    """
    # DEBUG: dump important POST data (sanitized)
    try:
        safe_post = {
            "requested_by_person_id": request.POST.get("requested_by_person_id"),
            "is_on_behalf": request.POST.get("is_on_behalf"),
            "on_behalf_of_person_id": request.POST.get("on_behalf_of_person_id"),
            "business_id": request.POST.get("business_id"),
            "request_document_type_id": request.POST.get("request_document_type_id"),
            "purpose_notes": request.POST.get("purpose_notes"),
            "line_document_purpose_id[]": request.POST.getlist("line_document_purpose_id[]"),
            "line_quantity[]": request.POST.getlist("line_quantity[]"),
            "line_offense_no[]": request.POST.getlist("line_offense_no[]"),
        }
        print("\n[WALKIN DEBUG] raw POST (sanitized):\n", json.dumps(safe_post, indent=2))
    except Exception as e:
        print("[WALKIN DEBUG] could not pretty-print POST:", e)

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
    purpose_rows = { r["document_purpose_id"]: r for r in _fetch_purposes_by_request_type(req_doc_type_id) }

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

    # Identify the doc type name & inject Business Clearance details if needed
    try:
        dt_row = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .eq("request_document_type_id", req_doc_type_id)
            .limit(1)
            .execute()
        )
        doc_type_name = (((dt_row.data or [{}])[0]) or {}).get("request_document_type_name") or ""
    except Exception:
        doc_type_name = ""

    if doc_type_name.strip().upper() in {BRGY_BUSINESS_DOC_NAME, "CERTIFIED TRUE COPY"}:
        if not business_id:
            messages.error(request, "Business is required for Barangay Business Clearance.")
            return redirect(f"{request.path.replace('/create/','/')}?request_document_type_id={req_doc_type_id or ''}")
        # Merge business/applicant fields into each line.details and tag the template override
        bc_details = _fetch_business_clearance_fields(business_id, subject_id or requested_by)
        for ln in lines:
            ln["details"] = {**(ln.get("details") or {}), **bc_details}
        print("[WALKIN DEBUG] lines after Business Clearance enrichment:\n", json.dumps(lines, indent=2, default=str))

    # Debug preview in client-shape for parity with mobile logs
    payload_client_shape = {
        "requested_by": requested_by,
        "on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
        "is_on_behalf": is_on_behalf,
        "business_id": business_id,
        "purpose_notes": purpose_notes,
        "lines": lines,
    }
    print("\n[WALKIN DEBUG] (client-shape) create_document_request_walkin payload:\n",
          json.dumps(payload_client_shape, indent=2, default=str))

    # ==== CALL THE WALK-IN RPC (NEW) ====
    staff_id = (request.session.get("auth") or {}).get("staff_id") or _staff_id(request)
    if not staff_id:
        messages.error(request, "Missing staff context. Please login again.")
        return redirect("clerk:walkin_new")

    walkin_args = {
        "p_requester_person_id": int(requested_by),
        "p_subject_person_id":   int(subject_id or requested_by),
        "p_business_id":         business_id,        # may be None
        "p_purpose_notes":       purpose_notes,      # may be None
        "p_lines":               lines,              # list; Supabase will JSON-encode to jsonb
        "p_clerk_user_id":       int(staff_id),
    }

    print("[WALKIN DEBUG] (rpc-shape) args sent to create_document_request_walkin:\n",
          json.dumps(walkin_args, indent=2, default=str))

    try:
        res = supabase.rpc("create_document_request_walkin", walkin_args).execute()
        print("[WALKIN DEBUG] RPC result .data :", getattr(res, "data", None))
        print("[WALKIN DEBUG] RPC result .error:", getattr(res, "error", None))
    except Exception as e:
        print("[WALKIN DEBUG] RPC raised:", e)
        messages.error(request, f"RPC failed: {e}")
        return redirect("clerk:walkin_new")

    if getattr(res, "error", None):
        messages.error(request, f"Supabase error: {escape(res.error.message)}")
        return redirect("clerk:walkin_new")

    # Function RETURNS int, but be defensive about shapes
    data = res.data
    new_id = None
    if isinstance(data, int):
        new_id = data
    elif isinstance(data, list) and data:
        first = data[0]
        new_id = first if isinstance(first, int) else (first.get("doc_request_id") if isinstance(first, dict) else None)
    elif isinstance(data, dict):
        new_id = data.get("doc_request_id") or data.get("id")

    if not new_id:
        messages.error(request, "Could not obtain new request ID from RPC.")
        return redirect("clerk:walkin_new")

    messages.success(request, f"Walk-in request created. ID: {new_id}")
    return redirect("clerk:detail", doc_request_id=new_id)



# ────────────────────────────────────────────────────────────
# SECTION: Confirm (PAID → FOR_PRINTING)
# ────────────────────────────────────────────────────────────

@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def confirm_request(request: HttpRequest, doc_request_id: int):
    """
    Confirm (PAID → FOR_PRINTING). If not fully paid, do nothing and advise to use
    the 'Confirm & Forward to Treasurer' action.
    """
    try:
        bundle = _fetch_bundle(doc_request_id)
    except APIError as e:
        messages.error(request, f"Unable to load request: {e}")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    header = (bundle or {}).get("header", {}) or {}
    payments = (bundle or {}).get("payments", {}) or {}

    amount_due  = float(header.get("amount_due") or 0)
    total_paid  = float(payments.get("total_paid") or 0)

    if total_paid + 1e-6 < amount_due:
        messages.warning(
            request,
            "This request is not fully paid yet. Use “Confirm & Forward to Treasurer”."
        )
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    # fully paid → move to FOR_PRINTING
    staff_id = 2
    err = confirm_and_send_to_printing(doc_request_id, int(staff_id), notes="Clerk confirmed (paid)")
    if err:
        messages.error(request, f"Failed to move to FOR PRINTING: {err}")
    else:
        messages.success(request, "Confirmed. Status is now FOR PRINTING.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

# ────────────────────────────────────────────────────────────
# NEW: Confirm & Forward to Treasurer (FOR_CLERK_REVIEW/PAID → FOR_TREASURER_REVIEW)
# ────────────────────────────────────────────────────────────
@session_login_required
@role_required(CLERK_ROLE)
@require_POST
def confirm_forward_treasurer(request: HttpRequest, doc_request_id: int):
    """
    Clerk confirm (FOR CLERK REVIEW/PAID → FOR_TREASURER_REVIEW).
    Always routes through the RPC that logs CONFIRMED_BY_CLERK and sets status.
    """
    staff_id = (request.session.get("auth") or {}).get("staff_id") or _staff_id(request)
    notes = (request.POST.get("reason") or "").strip() or None

    err = svc_confirm_forward_treasurer(doc_request_id, int(staff_id), notes)
    if err:
        messages.error(request, f"Failed to forward to Treasurer: {err}")
    else:
        messages.success(request, "Confirmed. Sent to Treasurer for payment review.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

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

def _norm_mobile(s: str | None) -> str | None:
    if not s:
        return None
    # Keep digits only, drop leading +63/0 normalization to last 10–11 digits
    digits = re.sub(r"\D+", "", s)
    if digits.startswith("63"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    # Return last 10 or 11 digits if present
    return digits[-11:] if len(digits) >= 11 else (digits[-10:] if len(digits) >= 10 else digits or None)

def _find_duplicate_owner(*, email: str | None, mobile: str | None,
                          last_name: str | None, first_name: str | None,
                          dob_iso: str | None, barangay: str | None, city: str | None) -> int | None:
    """
    Duplicate rules (short-circuit in this order):
      1) Exact email (case-insensitive)
      2) Normalized mobile match (digits, PH-friendly)
      3) Same LAST, FIRST, DOB — and same city+barangay if provided

    Returns person_id if found, else None.
    """
    email = (email or "").strip().lower() or None
    m_norm = _norm_mobile(mobile)

    with connection.cursor() as cur:
        # 1) Email (case-insensitive)
        if email:
            cur.execute("""
                SELECT person_id
                FROM person
                WHERE lower(coalesce(email,'')) = %s
                ORDER BY person_id DESC
                LIMIT 1
            """, [email])
            row = cur.fetchone()
            if row:
                return int(row[0])

        # 2) Mobile (normalized)
        if m_norm:
            cur.execute("""
                SELECT p.person_id
                FROM person p
                CROSS JOIN LATERAL (
                    SELECT regexp_replace(coalesce(p.mobile_num,''), '\\D+', '', 'g') AS p_digits
                ) d
                WHERE right(
                        CASE
                        WHEN d.p_digits LIKE '63%%' THEN substr(d.p_digits, 3)
                        WHEN d.p_digits LIKE '0%%'  THEN substr(d.p_digits, 2)
                        ELSE d.p_digits
                        END,
                        LEAST(GREATEST(length(
                            CASE
                            WHEN d.p_digits LIKE '63%%' THEN substr(d.p_digits, 3)
                            WHEN d.p_digits LIKE '0%%'  THEN substr(d.p_digits, 2)
                            ELSE d.p_digits
                            END
                        ), 10), 11)
                    ) = %s
                ORDER BY p.person_id DESC
                LIMIT 1
            """, [m_norm])
            row = cur.fetchone()
            if row:
                return int(row[0])

        # 3) Name + DOB (+ optional city/barangay to reduce false-positives)
        if last_name and first_name and dob_iso:
            params = [last_name.strip().upper(), first_name.strip().upper(), dob_iso]
            where_loc = ""
            if city:
                where_loc += " AND upper(coalesce(a.city,'')) = %s"
                params.append(city.strip().upper())
            if barangay:
                where_loc += " AND upper(coalesce(a.barangay,'')) = %s"
                params.append(barangay.strip().upper())

            cur.execute(f"""
                SELECT p.person_id
                FROM person p
                LEFT JOIN addresss a ON a.address_id = p.address_id
                WHERE upper(coalesce(p.last_name,''))  = %s
                  AND upper(coalesce(p.first_name,'')) = %s
                  AND p.birthdate = %s
                  {where_loc}
                ORDER BY p.person_id DESC
                LIMIT 1
            """, params)
            row = cur.fetchone()
            if row:
                return int(row[0])

    return None

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
    owner_form = BusinessOwnerInfo()
    biz_form = BusinessDetails()

    return {
        # Owner-side lookups
        "sex": _field_map(owner_form, "sex"),
        "civil_status": _field_map(owner_form, "civil_status"),
        "nationality": _field_map(owner_form, "nationality"),
        "religion": _field_map(owner_form, "religion"),

        # Business-side lookups
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
        "residency_name": res_name,
    }

def build_business_display(biz: dict, maps: Dict[str, Dict[int, str]]) -> Dict[str, Any]:
    """
    Return a label-rich dict strictly for display.
    """
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

def _save_temp_upload(upload, subdir: str) -> dict:
    """
    Save an uploaded file to default_storage under tmp/<subdir>/<uuid>_<name>.
    Returns a dict with storage 'path' plus metadata for later preview/upload.
    """
    if not upload:
        return {}

    # Build a storage-relative path like: "tmp/bizproof/uuid_name.jpg"
    fname = f"{uuid.uuid4().hex}_{upload.name}"
    storage_path = "/".join(["tmp", subdir.strip("/"), fname])

    # Write into whatever backend default_storage is configured to use
    default_storage.save(storage_path, ContentFile(upload.read()))

    return {
        "path": storage_path,                      # <-- use this everywhere
        "name": upload.name,
        "ctype": getattr(upload, "content_type", None),
        "size": getattr(upload, "size", None),
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

@session_login_required
@role_required(CLERK_ROLE)
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
@inject
def business_owner_nonresident(
    request: HttpRequest,
    resident_owner_service: IResidentOwnerService = Provide[AppContainer.resident_owner_service],
) -> HttpResponse:
    user_role = _auth_role_name(request)

    # Forms
    search_form = SearchBusinessOwner(request.GET or None)
    select_form = SelectOwnerForm(request.POST or None)  # for "Select as Owner" button
    create_form: BusinessOwnerInfo | None = None         # for Fill-up tab

    # Single source of truth for the current search term
    search = (request.GET.get("search") or request.POST.get("search") or "").strip()

    # --- SEARCH (non-residents only) ---
    results_payload: list[dict] = []
    if search:
        try:
            # Prefer kwarg if the service supports it, else fall back to a dedicated method
            try:
                rows = resident_owner_service.execute(search=search, only_nonresident=True)
            except TypeError:
                rows = getattr(resident_owner_service, "execute_nonresident")(search=search)

            # Normalize to the payload the template/JS expects
            results_payload = _normalize_owner_rows(rows)

            # DEBUG: log if no results so you can see what was searched
            if not results_payload:
                # use both print (visible in runserver) and logger (if configured)
                msg = f"[nonresident search] No results. term={search!r}, only_nonresident=True"
                print(msg, flush=True)
                log.info(msg)

        except Exception as e:
            # Keep the page responsive even if the repository errors out
            log.exception("Non-resident search failed for %r: %s", search, e)
            print(f"[nonresident search] ERROR for {search!r}: {e}", flush=True)
            results_payload = []

    selected = None

    if request.method == "POST" and "owner_person_id" in request.POST:
        # --- PATH A: selecting an existing person from search results ---
        if select_form.is_valid():
            try:
                owner_id = int(select_form.cleaned_data["owner_person_id"])
                selected = resident_owner_service.get_owner_details(owner_id)
            except Exception:
                log.exception(
                    "Fetching non-resident owner details failed for id=%s",
                    request.POST.get("owner_person_id"),
                )
                selected = None

        if selected:
            owner_payload = _owner_payload_common_from_dict(selected)
            # ensure display badge stays consistent
            owner_payload["residency_name"] = _normalize_residency_name(
                owner_payload.get("residency_name") or "NON-RESIDENT"
            )
            # Store ONLY JSON-safe types in session
            request.session["bizreg_owner"] = owner_payload
            request.session.set_expiry(1800)
            messages.success(request, "Owner selected. Continue with business details.")
        # If invalid, fall through and re-render with errors on search tab.

    elif request.method == "POST":
        # --- PATH B: fill-up / create flow ---
        create_form = BusinessOwnerInfo(request.POST, request.FILES or None)
        if create_form.is_valid():
            cd = create_form.cleaned_data

            # 0) Prepare raw fields for duplicate probing
            dob_val = cd["dob"]
            dob_str = dob_val.isoformat() if isinstance(dob_val, date) else str(dob_val)
            email   = (cd.get("email")   or "").strip() or None
            mobile  = (cd.get("mob_num") or "").strip() or None

            # 1) Duplicate check — short-circuit to existing PERSON if any
            dup_person_id = _find_duplicate_owner(
                email=email,
                mobile=mobile,
                last_name=cd["last_name"],
                first_name=cd["first_name"],
                dob_iso=dob_str,
                barangay=(cd.get("barangay") or "").strip() or None,
                city=(cd.get("city") or "").strip() or None,
            )

            if dup_person_id:
                # Fetch full details for display (best effort)
                try:
                    selected = resident_owner_service.get_owner_details(dup_person_id)
                except Exception:
                    selected = None

                dup_name = (getattr(selected, "full_name", None) or "Existing Person").strip() or "Existing Person"

                # Optional: preload results (same as before) so the Search tab is ready if user proceeds
                try:
                    preload_term = dup_name
                    preload_rows = resident_owner_service.execute(search=preload_term, only_nonresident=True)
                    results_payload = _normalize_owner_rows(preload_rows)
                    search_form = SearchBusinessOwner(initial={"search": preload_term})
                except Exception as _e:
                    print(f"[dup-check] preload search failed: {getattr(_e, 'args', _e)}", flush=True)

                # Build a target URL that lands on Search tab with the prefilled term
                target_url = (
                    reverse("clerk:business_owner_nonres")
                    + f"?tab=search&search={urlquote(preload_term if 'preload_term' in locals() else (search or ''))}"
                )

                # Re-render the SAME page (stay on Create tab) but with a flag to show the modal.
                return render(
                    request,
                    "business/business_owner_nonres.html",
                    {
                        "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
                        "page_title": "Business Owner Information",

                        # Search tab context (preloaded results so the tab is ready)
                        "search_form": search_form,
                        "search": (preload_term if 'preload_term' in locals() else search),
                        "results": results_payload,
                        "selected": None,

                        # Create tab context (keep the filled form)
                        "form": create_form,

                        # 🔔 NEW: modal flags + payload
                        "open_dup_modal": True,
                        "dup_modal": {
                            "name": dup_name,
                            "person_id": dup_person_id,
                            "target_url": target_url,
                        },
                    },
                )

            # 2) No duplicate → keep your original creation payload in session
            owner_payload: Dict[str, Any] = {
                "owner_person_id": cd.get("owner_person_id") or None,  # usually None for brand-new
                "last_name": cd["last_name"].strip(),
                "first_name": cd["first_name"].strip(),
                "middle_name": (cd.get("middle_name") or "").strip() or None,
                "suffix": (cd.get("suffix") or "").strip() or None,
                "dob": dob_str,  # JSON-safe string
                "email": email,
                "mobile": mobile,
                "sex_id": int(cd["sex"]),
                "civil_status_id": int(cd["civil_status"]),
                "nationality_id": int(cd["nationality"]),
                "religion_id": int(cd["religion"]),
                "street": cd["street"].strip(),
                "purok_sitio": (cd.get("purok_sitio") or "").strip(),
                "barangay": (cd["barangay"]).strip(),
                "city": (cd["city"]).strip(),
                "residency_name": "NON-RESIDENT",
            }

            request.session["bizreg_owner"] = owner_payload
            request.session.set_expiry(1800)
            messages.success(request, "Owner info saved. Continue with business details.")
            return redirect("clerk:business_details")
        else:
            # form errors: stay on create tab and show errors
            messages.error(request, "Please correct the errors below.")

    # Default create_form on GET (or when selection path used)
    if create_form is None:
        # IMPORTANT: copy before converting strings to date objects for form initial
        saved_raw = request.session.get("bizreg_owner") or {}
        saved = copy.deepcopy(saved_raw)  # <- do NOT mutate the session dict

        # Convert ISO string -> date only for the initial dict (keeps session JSON-safe)
        if "dob" in saved and isinstance(saved["dob"], str):
            try:
                saved["dob"] = date.fromisoformat(saved["dob"])
            except ValueError:
                pass

        create_form = BusinessOwnerInfo(initial=saved or None)

    # Keep search form pristine if invalid in GET
    if search and not search_form.is_valid():
        search_form = SearchBusinessOwner()

    return render(
        request,
        "business/business_owner_nonres.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            # Search tab context
            "search_form": search_form,
            "search": search,
            "results": results_payload,
            "selected": selected,
            # Create tab context
            "form": create_form,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@require_GET
@inject
def ajax_nonresident_owner_search(
    request: HttpRequest,
    resident_owner_service: IResidentOwnerService = Provide[AppContainer.resident_owner_service],
):
    q = (request.GET.get("search") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    try:
        rows = resident_owner_service.execute(search=q, only_nonresident=True)
    except TypeError:
        # Service doesn’t accept the kwarg; try a dedicated nonresident method if present
        fn = getattr(resident_owner_service, "execute_nonresident", None)
        rows = fn(search=q) if callable(fn) else []
    except Exception:
        rows = []

    return JsonResponse({"results": _normalize_owner_rows(rows)})

@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_details(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
):
    user_role = _auth_role_name(request)

    owner = request.session.get("bizreg_owner")
    if not owner:
        messages.warning(request, "No owner info found. Please fill the form first.")
        return redirect("clerk:business_owner")
    
    if request.method == "POST":
        form = BusinessDetails(request.POST, request.FILES or None)

        if form.is_valid():
            cd = form.cleaned_data

            payload: Dict[str, Any] = {
                # strings → strip safely
                "b_name": _sstrip(cd.get("b_name")) or "",
                "b_nature": _sstrip(cd.get("b_nature")),
                "b_address": _sstrip(cd.get("b_address")) or "",
                "b_desc": _sstrip(cd.get("b_desc")),
                "dti": _sstrip(cd.get("dti")),
                "inc_est": _sstrip(cd.get("inc_est")),

                # choice/ids
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

                # address modal fields
                "street": _sstrip(cd.get("street")) or "",
                "barangay": _sstrip(cd.get("barangay")) or "",
                "city": _sstrip(cd.get("city")) or "",

                # ✅ NEW: use ID for purok/sitio
                "purok_sitio_id": _to_int_or_none(cd.get("purok_sitio_id")),
                # (Optional) keep display label if your UI shows it in a review card
                "purok_sitio": _sstrip(cd.get("purok_sitio")) or "",
            }

            proof_pairs = []
            if request.FILES:
                files = request.FILES.getlist("proof") if "proof" in request.FILES else []
                for up in files:
                    info = _save_temp_upload(up, "bizproof")  # stores under tmp/bizproof/...
                    if info and info.get("path"):
                        proof_pairs.append(info)

            if proof_pairs:
                payload["proof_name"] = ", ".join(p["name"] for p in proof_pairs)
                payload["proof_tmp_pairs"] = proof_pairs

            # If user chose to continue despite duplicate warning, skip duplicate check
            is_ignore = (request.POST.get("action") or "").lower() == "ignore_duplicate"

            dup_biz_id: Optional[int] = None
            if not is_ignore:
                try:
                    owner = request.session.get("bizreg_owner") or {}
                    owner_person_id = _to_int_or_none(owner.get("owner_person_id") or owner.get("person_id"))

                    if owner_person_id:
                        # ✅ Use the repository/service (ID-based) instead of inline SQL
                        dup_biz_id = business_service.check_business_duplicate(
                            owner_person_id=owner_person_id,
                            business_name=payload["b_name"],
                            city=payload["city"],
                            barangay=payload["barangay"],
                            street=payload["street"],
                            purok_sitio_id=payload.get("purok_sitio_id"),
                            b_category_id=payload.get("b_category"),
                        )
                except Exception as e:
                    print("[dup-check] business duplicate check failed:", e, flush=True)
                    # Non-fatal: continue as if no duplicate

            if dup_biz_id:
                # 🚫 Do NOT redirect yet — render the same page and open a modal.
                form = BusinessDetails(initial=cd)

                addr_parts = [
                    payload.get("street") or "",
                    (payload.get("purok_sitio") or ""),  # label for display only
                    payload.get("barangay") or "",
                    payload.get("city") or "",
                ]
                addr_line = _join_addr(addr_parts)
                maps = fetch_display_maps_from_forms()
                b_category_id = payload.get("b_category")
                b_category_label = (maps.get("business_category", {}) or {}).get(b_category_id) or "—"

                owner_ctx = request.session.get("bizreg_owner") or {}

                return render(
                    request,
                    "business/business_details.html",
                    {
                        "page_path": f"{_auth_role_name(request)} / Business Records / Add Business / Business Information",
                        "page_title": "Business Information",
                        "form": form,
                        "owner": owner_ctx,

                        # Modal flags + data
                        "open_dup_modal": True,
                        "dup_modal": {
                            "business_id": dup_biz_id,
                            "business_name": payload["b_name"],
                            "business_category": b_category_label,
                            "address_line": addr_line,
                            "view_url": reverse("clerk:business_information", kwargs={"b_id": dup_biz_id}),
                        },

                        # Keep map/proof previews working on the page render
                        "proof_urls": [
                            (default_storage.url(p["path"]) if p.get("path") else None)
                            for p in (payload.get("proof_tmp_pairs") or [])
                            if p.get("path")
                        ],
                    },
                )

            # ✅ Either no duplicate, or user clicked "Continue anyway"
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
        return redirect("clerk:business_owner")

    business = request.session.get("bizreg_business")
    if not business:
        return redirect("clerk:business_details")
    
    if request.method == "POST":
        action = (request.POST.get("action") or "").lower()
        if action == "confirm_add":
            # Accept single or multiple files (template may use name="proof")
            uploads = []
            if "proof" in request.FILES:
                uploads = request.FILES.getlist("proof")

            if not uploads:
                for p in (business or {}).get("proof_tmp_pairs", []) or []:
                    spath = p.get("path")
                    if not spath:
                        continue
                    try:
                        # default_storage.open works across any backend (local/S3/Supabase)
                        uploads.append(default_storage.open(spath, "rb"))
                    except Exception:
                        pass

            lat_post = _to_float_or_none(request.POST.get("latitude"))
            lng_post = _to_float_or_none(request.POST.get("longitude"))
            if lat_post is not None:
                business["latitude"] = lat_post
            if lng_post is not None:
                business["longitude"] = lng_post

            cmd = RegisterBusinessProfileCmd(
                owner=owner,
                business=business,
                performer_staff_id=_auth_staff_id(request),
                proof_files_uploads=uploads,
            )

            try:
                business_id, owner_person_id = business_registration_service.business_registration(cmd)

                for p in (business or {}).get("proof_tmp_pairs", []) or []:
                    spath = p.get("path")
                    if spath:
                        try:
                            default_storage.delete(spath)
                        except Exception:
                            pass

                # try:
                #     notify_registration_received(owner=owner, business=business, business_id=business_id)
                # except Exception:
                #     pass

                # try:
                #     owner_mobile = (owner.get("mobile") or owner.get("mob_num") or "").strip()
                #     if owner_mobile:
                #         bname = (business.get("b_name") or "your business").strip()
                #         msg = (
                #             f"BARUG: Business Registration received for '{bname}'.\n"
                #             f"Ref: {business_id: 06d}.\n"
                #             f"Sign in to the mobile app to request the necessary business documents."
                #         )
                #         # fail_silently so we don't break the user flow
                #         send_sms(owner_mobile, msg, fail_silently=True)
                # except Exception:
                #     # fully swallow—logging optional
                #     pass

                request.session.pop("bizreg_owner", None)
                request.session.pop("bizreg_business", None)
                messages.success(request, f'Business #{business_id} created for owner #{owner_person_id}.')
                return redirect("clerk:business_information", b_id=business_id)
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

    tmp_pairs = (business.get("proof_tmp_pairs") or [])
    proof_urls = []
    for p in tmp_pairs:
        spath = p.get("path")
        if not spath:
            continue
        try:
            proof_urls.append(default_storage.url(spath))
        except Exception:
            # If your storage backend has no .url(), fall back to MEDIA_URL (dev only)
            url = (getattr(settings, "MEDIA_URL", "/media/").rstrip("/") + "/" + spath)
            proof_urls.append(url)

        
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
            "proof_urls": proof_urls,
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
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search= search,
        b_category= b_category,
        ownership_type= ownership_type,
        status= status,
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(request, "business/business_list.html", {
        'page_path': f'{user_role} / Business Records',
        'page_title': 'Business Records',
        'form' : form,
        'page_obj' : page_obj,
        'filters' : {
            'search' : search,
            'b_category' : b_category,
            'ownership_type' :ownership_type,
            'status' : status,
        },
        'url_name' : 'clerk:business_information',
        'search_url': 'clerk:ajax_business_search',
        'is_clerk': (user_role == CLERK_ROLE),
    })

AJAX_BUSINESS_PARTIALS = {
    # key      -> template path
    "cards": "business/_businesses.html",         # your map list cards
    "rows":  "business/_business_list.html",      # table rows for list page
}

@session_login_required
@role_required(CLERK_ROLE)
@require_GET
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
    
    tpl_key = (request.GET.get("tpl") or "cards").strip().lower()
    template_name = AJAX_BUSINESS_PARTIALS.get(tpl_key)
    if not template_name:
        return HttpResponseBadRequest("Unknown partial")

    q = request.GET.get("q", "") or None
    b_category = request.GET.get("b_category")
    ownership_type = request.GET.get("ownership_type")
    status = request.GET.get("status")

    rows = business_service.execute(
        search=q,
        b_category=_to_int_or_none(b_category),
        ownership_type=_to_int_or_none(ownership_type),
        status=_to_int_or_none(status),
    )[:50]

    base_ctx = {
        "url_name": "clerk:business_information",
    }

    context = {**base_ctx, ("rows" if tpl_key == "rows" else "cards"): rows}
    html = render_to_string(template_name, context, request=request)
    return HttpResponse(html)

@session_login_required
@role_required(CLERK_ROLE)
@nocache
@inject
def business_information(
    request, 
    b_id: int,
    business_info: IBusinessInfoService = Provide[AppContainer.owner_business_service],
    renewal_quote_svc: IBusinessRenewalQuoteService = Provide[AppContainer.business_renewal_quote_service],
) -> HttpResponse:
    user_role = _auth_role_name(request)
    
    person_id = request.GET.get("owner")
    person_id = int(person_id) if person_id and str(person_id).isdigit() else None

    dto = (
        business_info.execute(person_id=person_id, business_id=b_id)
        if person_id is not None
        else business_info.execute_by_business_id(b_id)  # see helper below
    )

    def _compose_owner_full_name(data: dict) -> str | None:
        last   = (data.get("last_name") or "").strip()
        first  = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()

        parts = []
        if last:
            parts.append(last.upper())                   # LAST
        if first:
            parts.append((", " if parts else "") + first.title())  # , First
        if middle:
            parts.append(" " + middle[:1].upper() + ".")           #  M.
        if suffix:
            parts.append(" " + suffix.upper())                     #  JR / III, etc.
        return "".join(parts) or None
    
    def _compose_full_address_from_owner(data: dict) -> str | None:
        street      = (data.get("street") or "").strip()
        sitio_purok = (data.get("sitio_purok") or "").strip()
        barangay    = (data.get("barangay") or "").strip()
        city        = (data.get("city") or "").strip()

        # Order strictly: STREET, PUROK/SITIO, BARANGAY, CITY
        parts = [p for p in [street, sitio_purok, barangay, city] if p]
        return ", ".join(parts) if parts else None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)
    owner["full_address"]    = _compose_full_address_from_owner(owner)

    operating_days = (dto.business.get("operating_days") or "").strip()  # e.g., "Mon, Tue, Wed"
    days = [d.strip() for d in operating_days.split(",")] if operating_days else []
    operating_days_start_name = days[0] if days else None
    operating_days_end_name = days[-1] if days else None

    formatted_id = f"{int(b_id):06d}"
    current_year = date.today().year

    grand_total, quote_rows, paid_rows = renewal_quote_svc.execute(business_id=b_id, year=current_year)

    business_dict = dict(dto.business or {})
    status_upper = (business_dict.get("business_status") or "").strip().upper()

    renewal_href = reverse("clerk:create_renewal_request", kwargs={"b_id": b_id})
    closure_href = reverse("clerk:initiate_business_closure", kwargs={"b_id": b_id})
    doc_req_href = reverse("clerk:walkin_new")

    try:
        _gt = grand_total if isinstance(grand_total, Decimal) else Decimal(str(grand_total or 0))
    except Exception:
        _gt = Decimal("0")
    has_dues = (_gt > 0)

    # Defaults
    show_summary_cta = False
    summary_cta_href = None
    summary_cta_label = None
    cta_mode = "link"

    if status_upper == "ACTIVE":
        if has_dues:
            # NEW: even if ACTIVE, show Renew/Pay action when there are dues
            show_summary_cta = True
            # summary_cta_href = renewal_href
            cta_mode = "selector"
            summary_cta_label = "Create Renewal Request"
        else:
            show_summary_cta = False
    elif status_upper == "PENDING":
        show_summary_cta = True
        cta_mode = "link"
        summary_cta_href = doc_req_href
        summary_cta_label = "Proceed to Document Request"
    elif status_upper == "EXPIRED":
        show_summary_cta = True
        # summary_cta_href = renewal_href
        cta_mode = "selector"
        summary_cta_label = "Create Renewal Request"
    else:
        # Fallback: show renewal CTA for other non-active statuses
        show_summary_cta = True
        cta_mode = "selector"
        summary_cta_label = "Continue"

    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {formatted_id}",
            "page_title": f"Business Details : {formatted_id}",
            "owner": owner,
            "business": dto.business,
            "business_files": (dto.business_proof or {}).get("files") or [],
            "operating_days_start_name": operating_days_start_name,
            "operating_days_end_name": operating_days_end_name,
            "grand_total": grand_total,
            "quote_rows": quote_rows,
            "paid_rows": paid_rows,
            "business_status_upper": status_upper,
            "show_summary_cta": show_summary_cta,
            "summary_cta_href": summary_cta_href,
            "summary_cta_label": summary_cta_label,
            "renewal_href": renewal_href,
            "closure_href": closure_href,
            "cta_mode": cta_mode,
        },
    )

@session_login_required
@role_required(CLERK_ROLE)
@csrf_protect
@nocache
@inject
def business_map_list(
    request: HttpRequest,
    business_service: IBusinessService = Provide[AppContainer.business_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)
    form = BusinessFilters(request.GET or None)

    search = request.GET.get("search")
    b_category = _to_int_or_none(request.GET.get("b_category"))
    ownership_type = _to_int_or_none(request.GET.get("ownership_type"))
    status = _to_int_or_none(request.GET.get("status"))

    rows = business_service.execute(
        search=search,
        b_category=b_category,
        ownership_type=ownership_type,
        status=status,
    )

    paginator = Paginator(rows, 5)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or b_category is not None or ownership_type is not None or status is not None) and not form.is_valid():
        form = BusinessFilters()

    return render(
        request,
        "business/business_map_list.html",
        {
            'page_path': f"{user_role} / Business Map",
            'page_title': "Business Map",
            'form': form,
            'page_obj' : page_obj,
            'filters' : {
                'search' : search,
                'b_category' : b_category,
                'ownership_type' :ownership_type,
                'status' : status,
            },
            "pins_url": reverse("clerk:api_business_pins"),
            'search_url': 'clerk:ajax_business_search',
        }
    )

@session_login_required
@role_required(CLERK_ROLE)
@nocache
@inject
def api_business_pins(
    request: HttpRequest,
    business_repo: IBusinessRepository = Provide[AppContainer.infra.business],
):
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")

    pins = business_repo.fetch_business_pins(
        search=(request.GET.get("search") or None),
        b_category=_to_int_or_none(request.GET.get("b_category")),
        ownership_type=_to_int_or_none(request.GET.get("ownership_type")),
        status=_to_int_or_none(request.GET.get("status")),
    )
    return JsonResponse(pins, safe=False)

@session_login_required
@role_required(CLERK_ROLE)
@csrf_protect
@nocache
@inject
def renewal_list(
    request: HttpRequest,
    business_renewal_repo: IBusinessRenewalService = Provide[AppContainer.business_renewal_service],
) -> HttpResponseRedirect | HttpResponsePermanentRedirect | HttpResponse:
    
    user_role = _auth_role_name(request)

    form = RenewalFilters(request.GET or None)

    search = request.GET.get("search")
    clearance_state = request.GET.get("clearance_state")

    rows = business_renewal_repo.execute(
        search=search,
        clearance_state=clearance_state
    )

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if (search or clearance_state is not None) and not form.is_valid():
        form = RenewalFilters()

    return render(request, "business/renewal_list.html", {
        'page_path': f'{user_role} / Resident List',
        'page_title': 'Resident List',
        'form' : form,
        'page_obj' : page_obj,
        'filters' : {
            'search' : search,
            'clearance_state' : clearance_state,
        },
        'url_name' : 'clerk:business_information',
        'search_url' : 'clerk:ajax_renewal_search',
    })

@session_login_required
@role_required(CLERK_ROLE)
@require_GET
@inject
def ajax_renewal_search(
    request:HttpRequest,
    business_renewal_repo: IBusinessRenewalService = Provide[AppContainer.business_renewal_service],
) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")
    
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return HttpResponseBadRequest("XHR required")

    q = request.GET.get("q", "") or None
    clearance_state = request.GET.get("clearance_state")

    rows = business_renewal_repo.execute(
        search=q,
        clearance_state=_to_int_or_none(clearance_state)
    )[:50]

    html = render_to_string(
        "business/_renewal_rows.html",
        {"rows": rows},
        request=request,
    )
    return HttpResponse(html, content_type="text/html; charset=utf-8")

@session_login_required
@role_required(CLERK_ROLE)
@inject
def create_renewal_request(
    request: HttpRequest,
    b_id: int,
    business_info: IBusinessInfoService = Provide[AppContainer.owner_business_service],
    renewal_quote_svc: IBusinessRenewalQuoteService = Provide[AppContainer.business_renewal_quote_service],
    svc: IBusinessRenewalRequestService = Provide[AppContainer.business_renewal_request_service],
):
    user_role = _auth_role_name(request)

    if request.method == "POST":
        try:
            business_id = int(request.POST.get("business_id") or b_id)
            period_type = (request.POST.get("period_type") or "ANNUAL").upper()
            period_year = int(request.POST.get("period_year") or date.today().year)

            # Quarter: only when QUARTERLY; accept "Q1"/"Q2"/... if provided
            raw_q = request.POST.get("period_quarter")
            period_quarter = None
            if period_type == "QUARTERLY" and raw_q:
                s = raw_q.strip().upper()
                if s.startswith("Q") and s[1:].isdigit():
                    period_quarter = int(s[1:])
                elif s.isdigit():
                    period_quarter = int(s)

            cmd = CreateRenewalRequestCmd(
                business_id=business_id,
                period_type=period_type,
                period_year=period_year,
                period_quarter=period_quarter,        # None for ANNUAL
                created_by_user_id=_auth_staff_id(request),
            )

            # NEW: create for ALL unpaid years up to period_year
            new_ids = svc.request_unpaid(cmd)  # returns List[int]

            if new_ids:
                ids_str = ", ".join(str(i) for i in new_ids)
                messages.success(
                    request,
                    f"Created {len(new_ids)} renewal request(s) for unpaid years up to {period_type} {period_year}: [{ids_str}] "
                    f"(status: FOR_TREASURER_REVIEW)."
                )
            else:
                messages.info(
                    request,
                    f"No unpaid {period_type} items found up to {period_year}. Nothing to create."
                )

            print(f"[create_renewal_request] Redirecting to business_information(b_id={business_id})", flush=True)
            return redirect("clerk:business_information", b_id=business_id)

        except Exception as e:
            try:
                post_dump = json.dumps({k: v for k, v in request.POST.items()}, default=str)
            except Exception:
                post_dump = str(dict(request.POST))
            print("\n[create_renewal_request][ERROR]:", repr(e), flush=True)
            print("[create_renewal_request][POST]:", post_dump, flush=True)
            traceback.print_exc()
            # user-facing message
            messages.error(request, f"Create renewal requests failed: {e}")
            return redirect("clerk:business_information", b_id=b_id)

    person_id = request.GET.get("owner")
    person_id = int(person_id) if person_id and str(person_id).isdigit() else None

    dto = (
        business_info.execute(person_id=person_id, business_id=b_id)
        if person_id is not None
        else business_info.execute_by_business_id(b_id)
    )

    def _compose_owner_full_name(data: dict) -> str | None:
        last   = (data.get("last_name") or "").strip()
        first  = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()

        parts = []
        if last:
            parts.append(last.upper())
        if first:
            parts.append((", " if parts else "") + first.title())
        if middle:
            parts.append(" " + middle[:1].upper() + ".")
        if suffix:
            parts.append(" " + suffix.upper())
        return "".join(parts) or None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)

    current_year = date.today().year

    grand_total, quote_rows, paid_rows = renewal_quote_svc.execute(business_id=b_id, year=current_year)

    def to_decimal(x):
        if x is None:
            return Decimal("0")
        return x if isinstance(x, Decimal) else Decimal(str(x))

    quote_rows = quote_rows or []
    base_sum  = sum(to_decimal(getattr(r, "base_fee", 0))   for r in quote_rows)
    surch_sum = sum(to_decimal(getattr(r, "surcharge", 0))  for r in quote_rows)
    header_status = ((dict(dto.business or {}).get("business_status") or "").strip().upper())
    clearance_year = current_year

    return render(request, "business/create_renewal_request.html", {
        'page_path' : f'{user_role} / Renewal Request',
        'page_title' : 'Renewal Request',
        "owner": owner,
        "business": dto.business,
        "grand_total": grand_total,
        "quote_rows": quote_rows,
        "paid_rows": paid_rows,
        "base_sum": base_sum,
        "surch_sum": surch_sum,
        "header_status": header_status,
        "clearance_year": clearance_year,
    })

@session_login_required
@role_required(CLERK_ROLE)
@inject
def initiate_business_closure(
    request: HttpRequest,
    b_id: int,
    business_info: IBusinessInfoService = Provide[AppContainer.owner_business_service],
    renewal_quote_svc: IBusinessRenewalQuoteService = Provide[AppContainer.business_renewal_quote_service],
):
    user_role = _auth_role_name(request)

    # Reuse the same DTO pattern used elsewhere
    dto = business_info.execute_by_business_id(b_id)

    def _compose_owner_full_name(data: dict) -> str | None:
        last   = (data.get("last_name") or "").strip()
        first  = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()
        parts = []
        if last:   parts.append(last.upper())
        if first:  parts.append((", " if parts else "") + first.title())
        if middle: parts.append(" " + middle[:1].upper() + ".")
        if suffix: parts.append(" " + suffix.upper())
        return "".join(parts) or None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)

    business = dto.business or {}
    header_status = ((business.get("business_status") or "").strip().upper())

    # NEW: compute outstanding dues (reusing renewal quote)
    current_year = date.today().year
    grand_total, quote_rows, paid_rows = renewal_quote_svc.execute(business_id=b_id, year=current_year)

    def _to_decimal(x):
        if x is None:
            return Decimal("0")
        return x if isinstance(x, Decimal) else Decimal(str(x))

    quote_rows = quote_rows or []
    base_sum  = sum(_to_decimal(getattr(r, "base_fee", 0))   for r in quote_rows)
    surch_sum = sum(_to_decimal(getattr(r, "surcharge", 0))  for r in quote_rows)
    has_dues  = (_to_decimal(grand_total) > 0)

    return render(request, "business/initiate_business_closure.html", {
        'page_path'    : f'{user_role} / Business Closure : {b_id:06d}',
        'page_title'   : f'Business Closure : {b_id:06d}',
        'business'     : business,
        'owner'        : owner,
        'header_status': header_status,

        # NEW context for dues display
        'grand_total'  : grand_total,
        'quote_rows'   : quote_rows,
        'base_sum'     : base_sum,
        'surch_sum'    : surch_sum,
        'has_dues'     : has_dues,
        'clearance_year': current_year,  # optional for display/consistency
    })

# clerk/views.py  (add)
@session_login_required
@role_required(CLERK_ROLE)
@nocache
@inject
def create_closure_payment_request(
    request: HttpRequest,
    b_id: int,
    business_info: IBusinessInfoService = Provide[AppContainer.owner_business_service],
    renewal_quote_svc: IBusinessRenewalQuoteService = Provide[AppContainer.business_renewal_quote_service],
    svc: IBusinessClosurePaymentRequestService = Provide[AppContainer.business_closure_payment_request_service],
) -> HttpResponse:
    user_role = _auth_role_name(request)

    if request.method == "POST":
        try:
            business_id   = int(request.POST.get("business_id") or b_id)
            period_type   = (request.POST.get("period_type") or "ANNUAL").upper()
            period_year   = int(request.POST.get("period_year") or date.today().year)

            raw_q = request.POST.get("period_quarter")
            period_quarter = None
            if period_type == "QUARTERLY" and raw_q:
                s = raw_q.strip().upper()
                if s.startswith("Q") and s[1:].isdigit(): period_quarter = int(s[1:])
                elif s.isdigit(): period_quarter = int(s)

            cmd = CreateRenewalRequestCmd(
                business_id=business_id,
                period_type=period_type,
                period_year=period_year,
                period_quarter=period_quarter,
                created_by_user_id=_auth_staff_id(request),
            )

            # Create per-unpaid-year requests (closure-payment flavor)
            new_ids = svc.request_unpaid(cmd)  # returns List[int]

            if new_ids:
                ids_str = ", ".join(str(i) for i in new_ids)
                messages.success(
                    request,
                    f"Created {len(new_ids)} closure payment request(s) up to {period_type} {period_year}: [{ids_str}] "
                    f"(status: FOR_TREASURER_REVIEW)."
                )
            else:
                messages.info(request, "No unpaid items found. Nothing to create.")

            return redirect("clerk:initiate_business_closure", b_id=business_id)
        except Exception as e:
            try:
                post_dump = json.dumps({k: v for k, v in request.POST.items()}, default=str)
            except Exception:
                post_dump = str(dict(request.POST))
            print("\n[create_closure_payment_request][ERROR]:", repr(e), flush=True)
            print("[create_closure_payment_request][POST]:", post_dump, flush=True)
            traceback.print_exc()
            messages.error(request, f"Create closure payment request failed: {e}")
            return redirect("clerk:initiate_business_closure", b_id=b_id)

    # GET — load summary UI
    dto = business_info.execute_by_business_id(b_id)

    def _compose_owner_full_name(data: dict) -> str | None:
        last = (data.get("last_name") or "").strip()
        first = (data.get("first_name") or "").strip()
        middle = (data.get("middle_name") or "").strip()
        suffix = (data.get("suffix") or "").strip()
        parts = []
        if last: parts.append(last.upper())
        if first: parts.append((", " if parts else "") + first.title())
        if middle: parts.append(" " + middle[:1].upper() + ".")
        if suffix: parts.append(" " + suffix.upper())
        return "".join(parts) or None

    owner = dict(dto.owner or {})
    owner["owner_full_name"] = _compose_owner_full_name(owner)

    current_year = date.today().year
    grand_total, quote_rows, paid_rows = renewal_quote_svc.execute(business_id=b_id, year=current_year)

    def to_dec(x):
        if x is None: return Decimal("0")
        return x if isinstance(x, Decimal) else Decimal(str(x))

    quote_rows = quote_rows or []
    base_sum  = sum(to_dec(getattr(r, "base_fee", 0))  for r in quote_rows)
    surch_sum = sum(to_dec(getattr(r, "surcharge", 0)) for r in quote_rows)

    header_status = ((dict(dto.business or {}).get("business_status") or "").strip().upper())
    clearance_year = current_year

    return render(request, "business/create_closure_payment_request.html", {
        'page_path' : f'{user_role} / Closure Payment Request',
        'page_title': 'Closure Payment Request',
        "owner": owner,
        "business": dto.business,
        "grand_total": grand_total,
        "quote_rows": quote_rows,
        "paid_rows": paid_rows,
        "base_sum": base_sum,
        "surch_sum": surch_sum,
        "header_status": header_status,
        "clearance_year": clearance_year,
    })

def renewal_request(request, b_id):
    user_role = _auth_role_name(request)

    return render(request, "business/renewal_request.html", {
        'page_path' : f'{user_role} / Renewal Request : {b_id}',
        'page_title' : f'Renewal Request : {b_id}',
    })
