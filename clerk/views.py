# ============================================================ 
# views.py — Clerk flows + Printing with Business Clearance map
# ============================================================

from __future__ import annotations

# ────────────────────────────────────────────────────────────
# SECTION: Imports
# ────────────────────────────────────────────────────────────
import datetime as dt
from uuid import uuid4
from typing import Any, Dict, List, Optional, Tuple
import io, os, zipfile, json, re
from datetime import datetime
from decimal import Decimal
import logging

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
from django.views.decorators.http import require_POST
from .forms import (
    SearchVerificationRequest, SearchBusinessOwner, SelectOwnerForm , BusinessOwnerInfo,
    BusinessDetails, BusinessFilters, RequestedDocsFilters
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

        # Is this a (CTC of) Barangay Business Clearance?
        is_bc = (
            doc_name_upper == BRGY_BUSINESS_DOC_NAME
            or (is_ctc and ((line.get("details") or {}).get("ctc_of","").strip().upper() == BRGY_BUSINESS_DOC_NAME))
        )

        # Template selection
        template_file = _choose_template(doc_name_print, False)
        if is_bc or (line.get("details") or {}).get("template_override") == BRGY_BUSINESS_PDF_FILE:
            template_file = BRGY_BUSINESS_PDF_FILE
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
def dashboard(request: HttpRequest):
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    return render(request, "clerk/dashboard.html", {
        "page_path": f"Barangay Clerk/Dashboard",
        "page_title": "Dashboard",
        "profile": profile,
        "auth": auth
    })

@session_login_required
@role_required(CLERK_ROLE)
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
@role_required(CLERK_ROLE)
@nocache
def person_submission_dets(request: HttpRequest, req_id: int):
    """Details of a single person's submitted verification + latest status."""
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
    """
    # Business core + address
    try:
        bq = (
            supabase.table("business")
            .select(
                "business_name, business_nature, capital_invested, prev_yr_total_gross_sales, "
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

    # Lines of business: split into up to 5 bullets
    nature = (b.get("business_nature") or "").strip()
    lob = [s.strip() for s in nature.split(",") if s.strip()]
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
# SECTION: Business screens (stubs; clerk-only)
# ────────────────────────────────────────────────────────────
BIZ_DRAFT_KEY = "biz_reg_draft"

def _auth_staff_id(request: HttpRequest) -> Optional[int]:
    return ((request.session.get("auth") or {}).get("staff_id")) or None

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

def _get_draft(request: HttpRequest) -> Dict[str, Any]:
    return request.session.get(BIZ_DRAFT_KEY) or {}

def _save_draft(request: HttpRequest, draft: Dict[str, Any]) -> None:
    request.session[BIZ_DRAFT_KEY] = draft
    request.session.modified = True

def _clear_draft(request: HttpRequest) -> None:
    if BIZ_DRAFT_KEY in request.session:
        del request.session[BIZ_DRAFT_KEY]
        request.session.modified = True

def _js(v):
    """Make values JSON-safe for Supabase RPC."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)                 # or str(v) if you prefer exact text
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()            # 'YYYY-MM-DD' / 'HH:MM:SS'
    return v

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
@session_login_required
@role_required(CLERK_ROLE)
@nocache
def business_owner(request: HttpRequest):
    user_role = (request.session.get("auth") or {}).get("role_name").title()
    return render(
        request,
        "business/business_owner.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner",
            "page_title": "Business Owner",
        },
    )

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_owner_resident(request: HttpRequest) -> HttpResponse:
    user_role = _auth_role_name(request)

    # allow "Change" to clear selection
    if request.GET.get("clear") == "1":
        draft = _get_draft(request)
        draft.pop("owner_person_id", None)
        _save_draft(request, draft)
        messages.info(request, "Selection cleared.")
        return redirect("clerk:business_owner_resident")

    # POST: selecting an owner
    search_form = SearchBusinessOwner(request.GET or None)
    select_form = SelectOwnerForm(request.POST or None)

    if request.method == "POST":
        if select_form.is_valid():
            owner_person_id = select_form.cleaned_data["owner_person_id"]
            draft = _get_draft(request)
            draft["owner_person_id"] = int(owner_person_id)
            _save_draft(request, draft)
            messages.success(request, "Owner selected. Review details below or continue.")
            return redirect("clerk:business_owner_resident")
        else:
            messages.error(request, "Please select a resident owner.")

    # GET: searching residents
    q = ""
    results: List[Dict[str, Any]] = []
    if search_form.is_bound and search_form.is_valid():
        q = (search_form.cleaned_data.get("search") or "").strip()
        if q:
            try:
                resp = supabase.rpc("search_person_by_code_or_name", {"p_key": q}).execute()
                results = resp.data or []
            except APIError as e:
                messages.error(request, f"Search error: {getattr(e,'message',str(e))}")

    # Load selected resident (if any)
    selected = None
    owner_person_id = (_get_draft(request) or {}).get("owner_person_id")
    if owner_person_id:
        try:
            sel = supabase.rpc("get_details", {"p_person_id": int(owner_person_id)}).execute()
            data = sel.data
            selected = (data[0] if isinstance(data, list) and data else data) or None
        except APIError as e:
            messages.error(request, f"Failed to load selected resident: {getattr(e,'message',e)}")

    return render(
        request,
        "business/business_owner_resident.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "search_form": search_form,  # GET form
            "select_form": select_form,  # POST form
            "q": q,
            "results": results,
            "selected": selected,
        },
    )

#DO NOT TOUCH THIS FUNCTION
def business_owner_nonresident(request: HttpRequest):
    user_role = (request.session.get("auth") or {}).get("role_name").title()
    form = BusinessOwnerInfo()
    return render(
        request,
        "business/business_owner_nonres.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "form": form,
        },
    )

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_details(request: HttpRequest) -> HttpResponse:
    user_role = _auth_role_name(request)
    staff_id = _auth_staff_id(request)
    if not staff_id:
        messages.error(request, "Missing staff context. Please log in again.")
        return redirect("login")

    # bucket from settings (required)
    BUCKET = getattr(settings, "SUPABASE_BUCKET", None)
    if not BUCKET:
        messages.error(request, "Storage bucket is not configured. Set SUPABASE_BUCKET in settings.")
        return redirect("clerk:business_owner_resident")

    draft = _get_draft(request)
    owner_person_id = draft.get("owner_person_id")
    if not owner_person_id:
        messages.warning(request, "Please choose a resident owner first.")
        return redirect("clerk:business_owner_resident")

    form = BusinessDetails(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data

            # upload proof file(s) to the configured bucket
            uploaded_paths: List[str] = []
            files = request.FILES.getlist("proof")
            for f in files:
                ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
                key = f"business-proofs/{uuid4().hex}.{ext}"
                try:
                    supabase.storage.from_(BUCKET).upload(
                        key, f.read(), {"content-type": f.content_type}
                    )
                    uploaded_paths.append(key)
                except Exception as e:
                    messages.error(request, f"Failed to upload proof '{f.name}': {e}")
                    return render(
                        request,
                        "business/business_details.html",
                        {
                            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
                            "page_title": "Business Information",
                            "form": form,
                        },
                    )
                
            # coerce ints from choices
            btype_id   = int(cd["b_type"])           if cd.get("b_type") else None
            own_id     = int(cd["ownership_type"])   if cd.get("ownership_type") else None
            day_start  = int(cd["opt_days_start"])   if cd.get("opt_days_start") else None
            day_end    = int(cd["opt_days_end"])     if cd.get("opt_days_end") else None
            has_clearance = (cd.get("prev_clearance") == "yes")

            payload = {
                "p_performer_staff_id": int(staff_id),
                "p_owner_person_id": int(owner_person_id),

                # business
                "p_business_name": cd.get("b_name"),
                "p_business_location_desc": cd.get("b_desc"),
                "p_business_nature": cd.get("b_nature"),

                "p_prev_yr_total_gross_sales": _js(cd.get("prevgross")),
                "p_date_est": _js(cd.get("date_est")),
                "p_dti_sec_reg_num": cd.get("dti"),
                "p_capital_invested": _js(cd.get("capital_invested")),
                "p_mnthly_gross_incom_est": _js(cd.get("inc_est")),
                "p_num_of_emp": cd.get("emp_num"),
                "p_has_business_clearance": has_clearance,

                "p_business_type_id": btype_id,
                "p_ownership_type_id": own_id,

                # operating schedule
                "p_operating_day_start": day_start,
                "p_operating_day_end": day_end,
                "p_operating_hour_start": _js(cd.get("opt_start")),
                "p_operating_hour_end": _js(cd.get("opt_end")),

                # business address
                "p_business_latitude": _js(cd.get("latitude")),
                "p_business_longitude": _js(cd.get("longitude")),
                "p_business_city": cd.get("city"),
                "p_business_barangay": cd.get("barangay"),
                "p_business_street": cd.get("street"),
                "p_business_purok_sitio_name": cd.get("purok_sitio"),

                # proofs
                "p_business_proof_files": uploaded_paths or None,
            }

            try:
                resp = supabase.rpc("register_business_and_owner", payload).execute()
                rows = resp.data or []
                if not rows:
                    messages.warning(request, "The server did not return IDs, but the request may have been processed.")
                else:
                    first = rows[0]
                    _ = first.get("business_id") if isinstance(first, dict) else first[0]
                    _ = first.get("owner_person_id") if isinstance(first, dict) else first[1]

                _clear_draft(request)
                messages.success(request, "Business registered successfully.")
                return redirect("clerk:business_list")

            except APIError as e:
                code = getattr(e, "code", None) or getattr(e, "error", None) or ""
                detail = getattr(e, "message", None) or str(e)
                if "P6057" in code or "P6057" in detail:
                    messages.error(request, "Invalid business type. Please pick a valid type.")
                elif "P6058" in code or "P6058" in detail:
                    messages.error(request, "Invalid ownership type. Please pick a valid type.")
                elif "P6061" in code or "P6061" in detail:
                    messages.error(request, "Invalid operating day range. Start must be ≤ End within 1..7.")
                elif "P6062" in code or "P6062" in detail:
                    messages.error(request, "Invalid operating hour range. Start time must be before end time.")
                elif "P6065" in code or "P6065" in detail:
                    messages.error(request, "Missing link type 'BUSINESS PROFILING'. Contact admin.")
                else:
                    messages.error(request, f"RPC error: {detail}")
        else:
            messages.error(request, "Please fix the errors in the Business Information form.")

    return render(
        request,
        "business/business_details.html",
        {
            "page_path": f"{user_role} / Business Records / Add Business / Business Information",
            "page_title": "Business Information",
            "form": form,
        },
    )

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_registration_reset(request: HttpRequest) -> HttpResponse:
    _clear_draft(request)
    messages.info(request, "Registration draft cleared.")
    return redirect("clerk:business_owner_resident")

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_list(request: HttpRequest):
    user_role = (request.session.get("auth") or {}).get("role_name").title()
    form = BusinessFilters()
    rows, rpc_error = [], None
    try:
        resp = supabase.rpc("get_business_summary", {}).execute()
        rows = resp.data or []
    except Exception as e:
        rpc_error = str(e)
        rows = []

    paginator = Paginator(rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_path": f"{user_role} / Business Records",
        "page_title": "Business Records",
        "form": form,
        "rows": rows,
        "rpc_error": rpc_error,
        "page_obj": page_obj,
    }

    return render(request, "business/business_list.html", context)

#DO NOT TOUCH THIS FUNCTION
@session_login_required
@role_required("Barangay Clerk")
@nocache
def business_information(request: HttpRequest, b_id: int):
    user_role = (request.session.get("auth") or {}).get("role_name").title()

    b_resp = supabase.rpc("get_business_details", {"p_business_id" : b_id}).execute()
    b_rows = b_resp.data or []
    b = b_rows[0] if b_rows else None

    raw_days = str(b.get("operating_days") or "").strip()
    operating_days_list = [d.strip() for d in raw_days.split(",") if d.strip()] if raw_days else []
    b["operating_days_list"] = operating_days_list

    owner = None
    owner_id = b.get("owner_person_id") or None

    if owner_id:
        p_resp = supabase.rpc("get_details", {"p_person_id" : owner_id}).execute()
        p_rows = p_resp.data or []
        owner = p_rows[0] if p_rows else None

    if not b:
        raise Http404(f"Business {b_id} not found.")

    return render(
        request,
        "business/business_information.html",
        {
            "page_path": f"{user_role} / Business Records / Business Details : {b_id}",
            "page_title": f"Business Details : {b_id}",
            "b": b,
            "owner" : owner,
        },
    )

#DO NOT TOUCH THIS FUNCTION
# Hannah's Code (kept as-is; unrelated to printing)
def business_owner_nonresident(request: HttpRequest):
    user_fullname, user_role_template = _profile_fallbacks(request)
    form = BusinessOwnerInfo()
    return render(
        request,
        "business/business_owner_nonres.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_fullname,
            "page_path": f"{user_fullname} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "user_role_template": user_role_template,
            "form": form,
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
