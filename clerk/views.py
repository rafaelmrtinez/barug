from __future__ import annotations

from typing import Any, Dict, List
from decimal import Decimal
import io, os, zipfile, json
from datetime import datetime, date

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils import timezone
from django.conf import settings

from postgrest.exceptions import APIError

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from authentication.supabase_client import supabase

from .forms import SearchVerificationRequest, SearchBusinessOwner, BusinessOwnerInfo, BusinessDetails, BusinessFilters

# pypdf for filling
try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject
except Exception:
    PdfReader = PdfWriter = None  # type: ignore

# =========================
# UI helpers / role guards
# =========================

STATUS_UI: Dict[str, Dict[str, str]] = {
    "FOR_TREASURER_REVIEW": {"label": "For Treasurer Review", "cls": "badge bg-warning-subtle text-warning-emphasis"},
    "PAID":                 {"label": "Paid",                 "cls": "badge bg-primary-subtle text-primary-emphasis"},
    "FOR_PRINTING":         {"label": "For Printing",         "cls": "badge bg-info-subtle text-info-emphasis"},
    "RELEASED":             {"label": "Released",             "cls": "badge bg-success-subtle text-success-emphasis"},
    "DECLINED":             {"label": "Declined",             "cls": "badge bg-danger-subtle text-danger-emphasis"},
}
CLERK_STATUSES_ALL = ["PAID", "FOR_PRINTING", "RELEASED", "DECLINED"]

def _titleize(s: str | None) -> str:
    return "" if not s else s.replace("_", " ").title()

def _staff_id(request: HttpRequest) -> int | None:
    prof = getattr(request, "profile", None)
    return getattr(prof, "staff_id", None) or request.session.get("staff_id")

def _has_role(request: HttpRequest, want: str) -> bool:
    prof = getattr(request, "profile", None)
    roles = set()
    if prof and getattr(prof, "roles", None):
        roles.update({str(r).upper() for r in prof.roles})
    if getattr(prof, "role", None):
        roles.add(str(prof.role).upper())
    if request.session.get("role_name"):
        roles.add(str(request.session["role_name"]).upper())
    return want.upper() in roles or ("CLERK" in roles if want.upper() == "CLERK" else False)

def _guard(request: HttpRequest) -> HttpResponse | None:
    if not _has_role(request, "CLERK"):
        return HttpResponseForbidden("Clerk access required.")
    if not _staff_id(request):
        return HttpResponseForbidden("Missing staff id.")
    return None


# =========================
# Small utils
# =========================

def pick(*vals, allow_zero: bool = False):
    """
    Return the first value that is not None and not an empty string.
    If allow_zero=True, a numeric 0 (or "0") is considered valid.
    """
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip() == "":
                continue
            if v.strip() == "0" and not allow_zero:
                continue
            return v
        if v == 0 and not allow_zero:
            continue
        return v
    return None

def _to_date(val) -> date | None:
    if not val:
        return None
    try:
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if "T" in s:  # ISO with time
            s = s.split("T", 1)[0]
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _calc_age_from_birthdate(bday_val) -> int | None:
    bday = _to_date(bday_val)
    if not bday: return None
    today = timezone.localdate()
    age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
    return max(age, 0)


def subject_view(header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide who the document is about. If on-behalf fields exist, use them;
    otherwise use the requester. Line-level overrides (subject_*) win.
    Also: if age is missing/0, compute from birthdate (incl. DB fetch fallback).
    """
    has_on_behalf = bool(header.get("on_behalf_of_person_id") or header.get("on_behalf_full_name"))

    full_name = pick(
        line.get("subject_full_name"),
        header.get("subject_full_name"),
        header.get("on_behalf_full_name") if has_on_behalf else header.get("requester_full_name"),
        header.get("requester_full_name"),
        header.get("resident_name"),
        header.get("full_name"),
    )

    address = pick(
        line.get("subject_address"),
        header.get("subject_address"),
        header.get("on_behalf_address") if has_on_behalf else header.get("address"),
        header.get("address"),
    )

    # Age: prefer explicit; else calculate from birthdate
    age = pick(
        line.get("subject_age"),
        header.get("subject_age"),
        header.get("on_behalf_age") if has_on_behalf else header.get("requester_age"),
        header.get("requester_age"),
        header.get("age"),
        allow_zero=True,
    )

    need_age_from_bday = (age is None or str(age).strip() == "" or str(age) == "0")
    if need_age_from_bday:
        bday = pick(
            line.get("subject_birthdate"),
            header.get("subject_birthdate"),
            header.get("on_behalf_birthdate") if has_on_behalf else header.get("requester_birthdate"),
            header.get("birthdate"),
        )
        if not bday and has_on_behalf and header.get("on_behalf_of_person_id"):
            try:
                # lightweight fetch; no schema change required
                p = supabase.table("person").select("birthdate").eq("person_id", header["on_behalf_of_person_id"]).single().execute()
                if getattr(p, "data", None):
                    bday = (p.data or {}).get("birthdate")
            except Exception:
                pass
        age_from_bday = _calc_age_from_birthdate(bday)
        if age_from_bday is not None:
            age = age_from_bday

    civil = pick(
        line.get("subject_civil_status"),
        header.get("subject_civil_status"),
        header.get("on_behalf_civil_status") if has_on_behalf else header.get("civil_status"),
        header.get("civil_status"),
    )

    nat = pick(
        line.get("subject_nationality"),
        header.get("subject_nationality"),
        header.get("on_behalf_nationality") if has_on_behalf else header.get("nationality"),
        header.get("nationality"),
    )

    return {
        "full_name": full_name or "",
        "address": address or "",
        "age": age if age is not None else "",
        "civil_status": civil or "",
        "nationality": nat or "",
        "is_on_behalf": has_on_behalf,
    }


# =========================
# Clerk — Queue / List
# =========================
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
        try: r["created_fmt"] = created_at.strftime("%b %d, %Y %H:%M")  # type: ignore
        except Exception: r["created_fmt"] = created_at

    paginator = Paginator(rows, 10)
    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))
    return render(request, "clerk/queue.html", {
        "page_obj": page_obj, "rows": page_obj.object_list,
        "q": q or "", "statuses": statuses, "statuses_all": CLERK_STATUSES_ALL,
        "active_count": len(statuses),
    })

# =========================
# Clerk — Detail
# =========================
def detail(request: HttpRequest, doc_request_id: int):
    bundle = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(bundle, "error", None):
        messages.error(request, f"Supabase error: {escape(bundle.error.message)}")
        return redirect("clerk:queue")

    data: Dict[str, Any] = bundle.data or {}
    header = data.get("header", {}) or {}
    lines = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline = data.get("timeline", []) or []

    # UI bits
    ui = STATUS_UI.get(header.get("status")) or {"label": header.get("status") or "—", "cls": "badge text-bg-secondary"}
    for l in lines:
        l["purpose_display"] = _titleize(l.get("purpose_code"))
        
        l["doc_purpose"] = (
            l.get("purpose_display")
            or l.get("purpose_label")
            or l.get("purpose")
            or (l.get("details") or {}).get("purpose_code")
         )

    # OR number for UI/PDF
    header["or_number"] = (
        payments.get("latest_or_number")
        or header.get("latest_or_number")
        or header.get("or_number")
        or ""
    )

    # Subject (display)
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
# PDF helpers
# =========================
def _pdf_templates_dir() -> str:
    base = getattr(settings, "PDF_TEMPLATES_DIR", None)
    return str(base) if base else str(getattr(settings, "BASE_DIR") / "pdf_templates")

def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)

def _date_parts(dt: datetime):
    return dt.strftime("%d"), dt.strftime("%B"), dt.strftime("%Y")

def _humanize_purpose(val: Any) -> str:
    s = _safe_str(val).strip()
    return _titleize(s) if s else ""

def _choose_template(doc_name: str, _is_minor_ignored: bool) -> str:
    """
    Always return the ADULT template, per requirement.
    """
    name = (doc_name or "").lower()
    if "indigency" in name or "indegency" in name:
        return "barangay-indegency.pdf"
    if "low" in name and "income" in name:
        return "barangay-cert-of-low-income.pdf"
    if "death" in name:
        return "barangay-death-cert.pdf"
    if "permit" in name:
        return "barangay-permit.pdf"
    # default
    return "barangay-clearance.pdf"

def _fill_fields_for_line(header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, str]:
    """
    Build field map for ADULT templates only (no minor variations).
    """
    now = timezone.localtime()
    d, m, y = _date_parts(now)

    subj = subject_view(header, line)   # single source of truth
    subject_full_name  = _safe_str(subj["full_name"])
    subject_addr       = _safe_str(subj["address"])
    subject_age        = _safe_str(subj["age"])           # can be "0"
    subject_civil      = _safe_str(subj["civil_status"])
    subject_nat        = _safe_str(subj["nationality"])

    barangay = "Señor Santo Niño"
    city     = _safe_str(header.get("city") or "Cebu City")
    province = _safe_str(header.get("province") or "Cebu")

    purpose = _humanize_purpose(
        line.get("purpose_display")
        or line.get("purpose_label")
        or line.get("purpose")
        or line.get("purpose_code")
        or (line.get("details") or {}).get("purpose_code")
    )

    line_total = _safe_str(pick(line.get("line_total"), "", allow_zero=True))
    or_no = _safe_str(
        pick(
            line.get("or_number"),
            header.get("or_number"),
            (header.get("payments") or {}).get("latest_or_number"),
        )
    )
    captain  = _safe_str(header.get("captain_name") or "Lourdes R. Ramirez")
    doc_name = _safe_str(line.get("document_type_name")).lower()

    # === Always adult mappings ===
    if "clearance" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "requestor_age": subject_age,
            "requestor_civil_status": subject_civil,
            "requestor_addr": subject_addr,
            "doc_purpose": purpose,
            "date_issued": d,
            "month_issued": m,
            "year_issued": y,
            "barangay_issued": barangay,
            "city_mun_issued": city,
            "province_issued": province,
            "brgy_captain": captain,
            "totla_amnt": line_total,
            "or_number": or_no,
        }

    if "indigency" in doc_name or "indegency" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "requestor_age": subject_age,
            "requestor_civil_status": subject_civil,
            "requestor_nationality": subject_nat,
            "requestor_barangay": barangay,
            "requestor_city_mun": city,
            "requestor_province": province,
            "requesition_purpose": purpose,
            "issued_date": d,
            "issued_month": m,
            "issued_year": y,
            "barangay_issued": barangay,
            "city_mun_issued": city,
            "province_issued": province,
            "brgy_captain": captain,
            "total_amnt": line_total,
            "or_number": or_no,
        }

    if "low" in doc_name and "income" in doc_name:
        return {
            "full_name": subject_full_name,
            "age": subject_age,
            "civil_status": subject_civil,
            "nationality": subject_nat,
            "barangay_name": barangay,
            "city_municipality": city,
            "province": province,
            "total_earning": _safe_str(line.get("monthly_income") or ""),
            "purpose": purpose,
            "day": d,
            "month": m,
            "year": y,
            "issued_at_brgy": barangay,
            "issued_at_city_municipality": city,
            "issued_at_province": province,
            "amnt": line_total,
            "official_reciept": or_no,
        }

    if "death" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "deceased_civil_status": subject_civil,
            "deceased_nationality": subject_nat,
            "deceased_barangay": barangay,
            "deceased_city_mun": city,
            "deceased_province": province,
            "date_of_death": _safe_str(line.get("death_day") or d),
            "month_of_death": _safe_str(line.get("death_month") or m),
            "year_of_death": _safe_str(line.get("death_year") or y),
            "place_of_death": _safe_str(line.get("place_of_death") or ""),
            "curr_date": d,
            "curr_month": m,
            "curr_year": y,
            "barangay_issued": barangay,
            "city_mun_issued": city,
            "province_issued": province,
            "brgy_captain": captain,
            "total_amnt": line_total,
            "or_number": or_no,
        }

    if "permit" in doc_name:
        event_dt = _safe_str(line.get("event_date_time") or "")
        return {
            "requestor_org": _safe_str(line.get("org_name") or ""),
            "requestor_name": subject_full_name,
            "requested_event": _safe_str(line.get("event_name") or ""),
            "event_location": _safe_str(line.get("event_location") or ""),
            "barangay_name": barangay,
            "brgy_date_time": event_dt,
            "issued_date": d,
            "issued_month": m,
            "issued_year": y,
            "barangay_issued": barangay,
            "cty_mun_issued": city,
            "province_issued": province,
            "brgy_capt": captain,
            "total_amnt": line_total,
            "or_number": or_no,
        }

    return {}

def _get_all_pdf_field_names(template_path: str) -> List[str]:
    names: List[str] = []
    if PdfReader is None: return names
    r = PdfReader(template_path)
    try:
        fdict = r.get_form_text_fields()  # pypdf 4.x
        if fdict: names.extend(list(fdict.keys()))
    except Exception:
        try:
            fdict = r.get_fields()
            if fdict: names.extend(list(fdict.keys()))
        except Exception:
            pass
    for page in r.pages:
        annots = page.get("/Annots")
        if not annots: continue
        for a in annots:
            obj = a.get_object()
            if obj.get("/Subtype") == "/Widget":
                nm = obj.get("/T")
                if nm:
                    nm = str(nm).strip("()")
                    if nm not in names: names.append(nm)
    return names

def _fill_pdf_with_values(template_path: str, merged: Dict[str, str]) -> bytes:
    if PdfReader is None: raise RuntimeError("pypdf is not installed. Run: pip install pypdf")
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"].update({NameObject("/NeedAppearances"): BooleanObject(True)})
    for page in writer.pages:
        writer.update_page_form_field_values(page, merged)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

# =========================
# Clerk — Actions (status + printing)
# =========================
def _set_status(doc_request_id: int, status: str, staff_id: int | None, reason: str | None = None) -> str | None:
    staff_id = 2  # TODO: wire _staff_id(request)
    if not staff_id: return "Missing staff id."
    res = supabase.rpc("forward_to_clerk_for_printing", {"p_doc_request_id": doc_request_id, "p_staff_id": staff_id, "p_reason": reason}).execute()
    return getattr(res, "error", None) and res.error.message


def mark_request_ready_for_pickup(request: HttpRequest, doc_request_id: int):
    if request.method != "POST":
        return redirect("clerk:detail", doc_request_id=doc_request_id)
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


def mark_for_printing(request: HttpRequest, doc_request_id: int):
    if request.method != "POST":
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    # 🚨 Removed: err = _set_status(doc_request_id, "FOR_PRINTING", _staff_id(request))
    # 🚨 Removed: marking logic
    # Now it ONLY downloads

    do_download = (request.POST.get("download") == "1")
    include_debug = (request.POST.get("debug") == "1")

    # Always fetch details for download
    bundle = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(bundle, "error", None):
        messages.error(request, f"Supabase error: {escape(bundle.error.message)}")
        return redirect("clerk:detail", doc_request_id=doc_request_id)
    
    data: Dict[str, Any] = bundle.data or {}
    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []

    payments = data.get("payments", {}) or {}
    # Make OR number available to the field-mapper
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
        # Always use the ADULT template
        template_file = _choose_template(doc_name, False)
        template_path = os.path.join(base_dir, template_file)
        exists = os.path.exists(template_path)
        if not exists:
            alt = os.path.join(settings.BASE_DIR, "clerk", "pdf_templates", template_file)
            if os.path.exists(alt):
                template_path, exists = alt, True
        if not exists:
            print(json.dumps({
                "doc_index": idx, "doc_name": doc_name, "template_file": template_file,
                "template_path": template_path, "exists": False, "reason": "Template not found"
            }, indent=2))
            continue

        # Build values and merge with placeholders
        base_values = _fill_fields_for_line(header, line)
        field_names = _get_all_pdf_field_names(template_path)
        merged = {name: (base_values.get(name) if str(base_values.get(name) or "").strip() else "No data")
                  for name in field_names}
        missing = [n for n in field_names if n not in base_values or str(base_values.get(n) or "").strip() == ""]

        # Structured debug
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

        # detailed debug item for optional JSON file
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

    # Single PDF no-debug => return PDF
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

    # Otherwise ZIP
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

    resp = HttpResponse(zbuf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{header.get("request_code","REQ")}-documents.zip"'
    return resp


def mark_released(request: HttpRequest, doc_request_id: int):
    if request.method != "POST":
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    # Check current status first
    try:
        bundle = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
        if getattr(bundle, "error", None):
            messages.error(request, f"Supabase error: {escape(bundle.error.message)}")
            return redirect("clerk:detail", doc_request_id=doc_request_id)
        header = (bundle.data or {}).get("header", {}) or {}
        current_status = (header.get("status") or "").upper()
    except Exception:
        messages.error(request, "Failed to verify request status.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    if current_status != "READY FOR PICKUP":
        messages.error(request, "Cannot mark as RELEASED. Request must be READY_FOR_PICKUP first.")
        return redirect("clerk:detail", doc_request_id=doc_request_id)

    # proceed with release
    staff_id = _staff_id(request)
    reason   = (request.POST.get("reason") or "").strip() or None
    res = supabase.rpc("mark_request_released", {"p_doc_request_id": doc_request_id, "p_staff_id": staff_id, "p_reason": reason}).execute()
    if getattr(res, "error", None):
        messages.error(request, f"Failed: {escape(res.error.message)}")
    else:
        messages.success(request, "Marked as released.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)


def decline(request: HttpRequest, doc_request_id: int):
    if request.method != "POST":
        return redirect("clerk:detail", doc_request_id=doc_request_id)
    if (g := _guard(request)): return g
    reason = (request.POST.get("reason") or "").strip() or None
    err = _set_status(doc_request_id, "DECLINED", _staff_id(request), reason)
    messages.error(request, f"Failed: {escape(err)}") if err else messages.success(request, "Request declined.")
    return redirect("clerk:detail", doc_request_id=doc_request_id)

# =========================
# Identity verification (unchanged)
# =========================
STATUS_APPROVED = 3
STATUS_REJECTED = 4
STATUS_DECLINE  = 7

@session_login_required
@role_required("Barangay Clerk")
@nocache
def dashboard(request: HttpRequest):
    profile = getattr(request, "person_profile", None)
    return render(request, "dashboard.html", {"page_title": "Dashboard", "profile": profile})

@session_login_required
@role_required("Barangay Clerk")
@nocache
def review_approve(request: HttpRequest):
    auth = request.session.get("auth")
    profile = getattr(request, "person_profile", None)
    form = SearchVerificationRequest(request.GET or None)
    search = (form.cleaned_data.get("search") if form.is_valid() else "") if request.GET else ""
    resp = supabase.rpc("get_id_validation_requests", {}).execute()
    rows = resp.data or []
    if search:
        q = search.lower().strip()
        rows = [r for r in rows if q in f"{r.get('requester_first_name','')} {r.get('requester_last_name','')}".lower()
                or q in (r.get("latest_status","") or "").lower()]
    paginator = Paginator(rows, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "resident/identity_verification_list.html", {
        "page_path": "Barangay Clerk / Account Verification", "page_title": "Account Verification",
        "page_obj": page_obj, "form": form, "profile": profile, "auth": auth,
    })

def person_submission_dets(request: HttpRequest, req_id: int):
    resp = supabase.rpc("get_details", {"p_person_id": req_id}).execute()
    data = resp.data or []
    if not data: raise Http404("Details not found.")
    person = data[0]
    try:
        sresp = supabase.rpc("get_id_validation_requests", {}).execute()
        srows = sresp.data or []
        status_row = next((r for r in srows if r.get("requester_person_id") == req_id), None)
    except APIError:
        status_row = None
    if status_row:
        person["latest_status"] = status_row.get("latest_status") or "APPROVED"
        person["latest_remarks"] = status_row.get("latest_remarks")
        person["approved_date"] = status_row.get("approved_date")
    return render(request, "clerk/resident/person_submission_dets.html", {
        "page_path": f"Clerk / Account Verification : {req_id}",
        "page_title": f"Account Verification : {req_id}",
        "person": person,
    })

def _rpc_approve_person_by_clerk(request: HttpRequest, person_id: int, status_id: int, remarks: str | None):
    auth = request.session.get("auth") or {}
    staff_id = auth.get("staff_id") or _staff_id(request)
    if not staff_id: raise Http404("Staff not found in session.")
    payload = {"p_clerk_staff_id": staff_id, "p_person_id": person_id, "p_status_id": status_id, "p_remarks": remarks}
    try:
        return supabase.rpc("approve_person_by_clerk", payload).execute()
    except APIError as e:
        try: msg = e.message.get("message")
        except Exception: msg = str(e)
        raise APIError({"message": msg or "Update failed."})

@session_login_required
@role_required("Barangay Clerk")
@nocache
def approve_request(request: HttpRequest, req_id: int):
    if request.method != "POST": raise Http404()
    try:
        _rpc_approve_person_by_clerk(request, req_id, STATUS_APPROVED, None)
        messages.success(request, "Request approved.")
    except APIError as e:
        try: messages.warning(request, e.message.get("message"))
        except Exception: messages.warning(request, "This request cannot be approved.")
    return redirect("clerk:person_details", req_id=req_id)

@session_login_required
@role_required("Barangay Clerk")
@nocache
def decision_request(request: HttpRequest, req_id: int):
    if request.method != "POST": raise Http404()
    action = (request.POST.get("action") or "").lower()
    remarks = (request.POST.get("remarks") or "").strip()
    if action not in ("reject","decline"):
        messages.error(request, "Invalid action.")
        return redirect("clerk:person_details", req_id=req_id)
    if not remarks:
        messages.error(request, "Remarks are required.")
        return redirect("clerk:person_details", req_id=req_id)
    status_id = STATUS_REJECTED if action=="reject" else STATUS_DECLINE
    try:
        _rpc_approve_person_by_clerk(request, req_id, status_id, remarks)
        messages.success(request, f"Request marked as {'Rejected' if status_id==STATUS_REJECTED else 'Declined'}.")
    except APIError as e:
        try: messages.warning(request, e.message.get("message"))
        except Exception: messages.warning(request, "This request cannot be updated right now.")
    return redirect("clerk:person_details", req_id=req_id)

# =========================
# Business screens (stubs; made safe)
# =========================
def _profile_fallbacks(request: HttpRequest):
    user_role = (request.session.get("auth") or {}).get("role_name")
    user_role_template = user_role.lower().replace(" ", "_")
    return user_role.title(), user_role_template

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

def business_owner_nonresident(request: HttpRequest):
    user_fullname, user_role, user_role_template = _profile_fallbacks(request)
    form = BusinessOwnerInfo()
    return render(
        request,
        "business/business_owner_nonres.html",
        {
            "user_fullname": user_fullname,
            "user_role": user_role,
            "page_path": f"{user_role} / Business Records / Add Business / Business Owner Information",
            "page_title": "Business Owner Information",
            "user_role_template": user_role_template,
            "form": form,
        },
    )

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
@role_required("Barangay Clerk")
@nocache
def business_list(request: HttpRequest):
    user_role, user_role_template = _profile_fallbacks(request)
    form = BusinessFilters()

    resp = supabase.rpc("get_business_summary", {}).execute()
    rows = resp.data or []

    paginator = Paginator(rows, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "business/business_list.html",
        {
            "page_path": f"{user_role} / Business Records",
            "page_title": "Business Records",
            "user_role_template": user_role_template,
            "form": form,
            "rows": rows,
            "page_obj": page_obj,
        },
    )

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
