# clerk/services/clerk_service.py
from __future__ import annotations

import io
import os
import re
import json
import zipfile
import datetime as dt
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone
from postgrest.exceptions import APIError

# ── Supabase + existing service helpers
from authentication.supabase_client import supabase
from common.send_email import send_email

from ..services.requests_service import _fetch_bundle, _set_status
from ..services.subject_service import subject_view
from ..services.pdf_service import (
    _pdf_templates_dir,
    _get_all_pdf_field_names,
    _fill_pdf_with_values,
    _choose_template,
    _safe_str,
    BUSINESS_CLEARANCE_FIELD_MAP,
)

# ────────────────────────────────────────────────────────────
# Business Clearance constants
# ────────────────────────────────────────────────────────────
BRGY_BUSINESS_DOC_NAME = "BARANGAY BUSINESS CLEARANCE"
BRGY_BUSINESS_PDF_FILE = "barangay-business-clearance.pdf"

# ────────────────────────────────────────────────────────────
# Small utilities (logic only—no rendering)
# ────────────────────────────────────────────────────────────
def titleize(s: Optional[str]) -> str:
    return "" if not s else s.replace("_", " ").title()

def _parse_dt_any(val: Any) -> Optional[datetime]:
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
                try:
                    d = dt.date.fromisoformat(s[:10])
                    return datetime(d.year, d.month, d.day, tzinfo=timezone.get_current_timezone())
                except Exception:
                    return None
    except Exception:
        return None
    return None

def friendly_date_text(val: Any) -> Optional[str]:
    d = _parse_dt_any(val)
    if not d:
        return None
    try:
        try:
            d_local = timezone.localtime(d)
        except Exception:
            d_local = d
        return d_local.strftime("%B %d, %Y")
    except Exception:
        return None

def _resolve_person_id_from_header(header: Dict[str, Any]) -> Optional[int]:
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

def _lookup_person_contact(person_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    if not person_id:
        return None, None
    try:
        res = (
            supabase.table("person")
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
        return full, email
    except Exception:
        return None, None

def send_ready_for_pickup_email(header: Dict[str, Any], lines: List[Dict[str, Any]]) -> Tuple[bool, str]:
    person_id = _resolve_person_id_from_header(header)
    full_name, email = _lookup_person_contact(person_id)
    if not email:
        return False, "No email on file for this resident. Notification not sent."

    req_code  = header.get("request_code") or f"REQ-{header.get('doc_request_id','')}"
    doc_names = [ (l.get("document_type_name") or "").strip() for l in (lines or []) if (l.get("document_type_name") or "").strip() ]
    docs_str  = ", ".join(doc_names) if doc_names else "your requested document(s)"

    barangay_name = getattr(settings, "BRGY_NAME", "Barangay Sto. Niño")
    pickup_info   = getattr(settings, "BRGY_PICKUP_INFO", "Please proceed to the Barangay Office during office hours.")

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

    result = send_email(
        subject=subject,
        to=[(full_name or "", email)],
        body_text=body_txt,
        body_html=body_html,
        from_name=barangay_name,
        fail_silently=False,
    )
    return (True, f"Email notification sent to {email}.") if getattr(result, "ok", False) \
           else (False, "Failed to send email notification at this time.")

# ────────────────────────────────────────────────────────────
# Clerk queue + details
# ────────────────────────────────────────────────────────────
def get_doc_types_all() -> List[str]:
    try:
        res = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .order("request_document_type_name")
            .execute()
        )
        return [
            (r.get("request_document_type_name") or "").strip()
            for r in (res.data or [])
            if (r.get("request_document_type_name") or "").strip()
        ]
    except Exception:
        return []

def fetch_queue_rows(q: Optional[str], statuses: List[str], doc_types: List[str]) -> List[Dict[str, Any]]:
    query = (
        supabase.table("v_doc_request_list_ex")
        .select("*")
        .order("doc_request_id", desc=True)
    )
    if statuses:
        query = query.in_("status", statuses)
    if q:
        array_probe = "{" + q + "}"
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.ov.{array_probe},purposes.ov.{array_probe}")

    rows = (query.limit(200).execute().data) or []

    # optional filter by doc_types list (in-memory)
    if doc_types:
        selected = {str(d).strip().lower() for d in doc_types}
        def _overlaps(row: Dict[str, Any]) -> bool:
            vals = row.get("doc_types") or []
            have = {str(v).strip().lower() for v in vals if v}
            return bool(have & selected)
        rows = [r for r in rows if _overlaps(r)]

    # Enrich display-ish fields (still logic, not template work)
    for r in rows:
        r["purposes_display"] = [titleize(p) for p in (r.get("purposes") or [])]
        fn = (r.get("requester_first_name") or r.get("first_name") or "").strip()
        ln = (r.get("requester_last_name") or r.get("last_name") or "").strip()
        full = (r.get("requester_full_name") or r.get("resident_name") or "").strip() or " ".join([fn, ln]).strip()
        r["requester_display"] = full or None
    return rows

def get_detail_bundle(doc_request_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    data = _fetch_bundle(doc_request_id)
    header = data.get("header", {}) or {}
    lines = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}
    timeline = data.get("timeline", []) or []

    # expose receipt info to PDFs / details
    header["or_number"] = (
        payments.get("latest_or_number")
        or header.get("latest_or_number")
        or header.get("or_number")
        or ""
    )
    # defensive default for amount
    header["paid_amount"] = payments.get("latest_amount") or payments.get("amount")
    header["paid_date"]   = payments.get("latest_paid_at") or payments.get("paid_at") or payments.get("latest_or_time")

    for l in lines:
        l["purpose_display"] = titleize(l.get("purpose_code"))
        l["doc_purpose"] = (
            l.get("purpose_display")
            or l.get("purpose_label")
            or l.get("purpose")
            or (l.get("details") or {}).get("purpose_code")
        )

    subj = subject_view(header, {})
    header["is_on_behalf"]        = subj["is_on_behalf"]
    header["subject_full_name"]   = subj["full_name"]
    header["subject_address"]     = subj["address"]
    header["subject_age"]         = subj["age"]
    header["subject_civil_status"]= subj["civil_status"]
    header["subject_nationality"] = subj["nationality"]

    return header, lines, payments, timeline

# ────────────────────────────────────────────────────────────
# Status changes
# ────────────────────────────────────────────────────────────
def mark_ready_for_pickup(doc_request_id: int, staff_id: Optional[int], reason: Optional[str]) -> Tuple[bool, str]:
    # First call the RPC
    res = supabase.rpc("mark_request_ready_for_pickup", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        return False, f"Failed: {res.error.message}"

    # Then send email
    try:
        bundle = _fetch_bundle(doc_request_id)
    except APIError as e:
        # status already updated; email may still fail silently with info
        return True, f"Marked as ready for pickup, but email fetch failed: {getattr(e, 'message', str(e))}"

    ok, info = send_ready_for_pickup_email(bundle.get("header") or {}, bundle.get("lines") or [])
    return True, info if ok else f"Marked as ready for pickup. {info}"

def _apply_pdf_field_mapping(doc_name: str, field_names: List[str], values: Dict[str, Any], include_debug: bool = False) -> Dict[str, Any]:
    nm = (doc_name or "").strip().upper()
    if nm != BRGY_BUSINESS_DOC_NAME:
        return {fn: values.get(fn) for fn in field_names}

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
            if include_debug:
                mapped.setdefault(pdf_field, pdf_field)  # print field names inside PDF
            # Dev console hints (kept server-side)
            if skey in advice:
                print(f"[PRINT ADVICE] Missing '{skey}'. {advice[skey]}")
        else:
            mapped[pdf_field] = val
    return mapped

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

    # Lines of business: up to 5 items
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
        "template_override": BRGY_BUSINESS_PDF_FILE,
    }
    return details

def generate_documents_package(doc_request_id: int, include_debug: bool) -> Dict[str, Any]:
    """
    Returns:
      {"mode":"single","bytes":..., "filename": ..., "headers": {...}}
       or
      {"mode":"zip","bytes":..., "filename": ...}
    """
    data = _fetch_bundle(doc_request_id)
    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}

    # receipt exposure
    header["or_number"] = (
        payments.get("latest_or_number")
        or payments.get("or_number")
        or _safe_str(header.get("or_number"))
    )
    # prefer recomputed line total if present
    try:
        line_total = sum(float(line.get("line_total", 0) or 0) for line in lines)
    except Exception:
        line_total = 0.0
    header["paid_amount"] = line_total or payments.get("amount")
    header["paid_date"]   = payments.get("latest_paid_at") or payments.get("paid_at") or payments.get("latest_or_time")

    outputs: List[tuple[str, bytes]] = []
    debug_items: List[Dict[str, Any]] = []
    base_dir = _pdf_templates_dir()

    for idx, line in enumerate(lines, start=1):
        doc_name = _safe_str(line.get("document_type_name") or f"doc-{idx}")
        template_file = _choose_template(doc_name, False)
        det = (line.get("details") or {})
        if (doc_name.strip().upper() == BRGY_BUSINESS_DOC_NAME) or (det.get("template_override") == BRGY_BUSINESS_PDF_FILE):
            template_file = BRGY_BUSINESS_PDF_FILE

        # Resolve path
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

        # Build values
        base_values = _fill_fields_for_line(header, line)
        detail_values = (line.get("details") or {})
        combined_values = {**detail_values, **base_values}

        # Subject/applicant fallbacks
        try:
            _subj = subject_view(header, line)
            combined_values.setdefault("applicant_full_name", _safe_str(_subj.get("full_name")))
            combined_values.setdefault("applicant_age", _safe_str(_subj.get("age")))
            combined_values.setdefault("applicant_nationality", _safe_str(_subj.get("nationality")))
        except Exception as e:
            print(f"[PRINT DEBUG] subject fallbacks failed: {e}")

        # meta boxes
        combined_values["numberfour"] = header.get("request_code")

        created_any = header.get("created_at") or header.get("created_ts") or header.get("date_created")
        friendly_applied = friendly_date_text(created_any)
        combined_values["numberfive"] = friendly_applied or _safe_str(created_any)
        combined_values.setdefault("numbersixteen", header.get("captain_name") or "Lourdes R. Ramirez")
        combined_values.setdefault("year_issued", timezone.localtime().strftime("%Y"))

        # ensure payment fields
        combined_values.setdefault("paid_amount", header.get("paid_amount"))
        combined_values["paid_date"] = friendly_date_text(header.get("paid_date")) if header.get("paid_date") else None
        combined_values.setdefault("or_number", header.get("or_number"))

        # print-time BC enrich if missing
        if doc_name.strip().upper() == BRGY_BUSINESS_DOC_NAME:
            bc_keys = ["business_name_style", "business_address", "capital_invested", "gross_sales_prev_year"]
            needs_enrich = any(not _safe_str(combined_values.get(k)).strip() for k in bc_keys)
            if needs_enrich:
                bid = header.get("business_id")
                if not bid:
                    try:
                        r = (
                            supabase.table("document_request")
                            .select("business_id")
                            .eq("doc_request_id", doc_request_id)
                            .limit(1)
                            .execute()
                        )
                        bid = ((r.data or [{}])[0] or {}).get("business_id")
                    except Exception as e:
                        print(f"[PRINT DEBUG] could not fetch business_id for request {doc_request_id}: {e}")
                subj_pid = header.get("subject_person_id") or header.get("requested_by_person_id")
                if bid:
                    try:
                        bc_enrich = _fetch_business_clearance_fields(int(bid), int(subj_pid) if subj_pid else None)
                        combined_values = {**bc_enrich, **combined_values}
                    except Exception as e:
                        print(f"[PRINT DEBUG] business fallback failed: {e}")

        field_names = _get_all_pdf_field_names(template_path)
        values_mapped = _apply_pdf_field_mapping(doc_name, field_names, combined_values, include_debug)

        merged = {
            name: (values_mapped.get(name) if str(values_mapped.get(name) or "").strip() else "No data")
            for name in field_names
        }

        # Generate PDF bytes
        try:
            pdf_bytes = _fill_pdf_with_values(template_path, merged)
        except Exception:
            with open(template_path, "rb") as f:
                pdf_bytes = f.read()

        safe_name = doc_name.lower().replace(" ", "-")
        out_name = f"{header.get('request_code','REQ')}-{safe_name}.pdf"
        outputs.append((out_name, pdf_bytes))
        if include_debug:
            debug_items.append({
                "output_filename": out_name,
                "doc_name": doc_name,
                "template_file": template_file,
                "template_path": template_path,
                "field_names": field_names,
                "values_written": merged,
            })

    if not outputs:
        raise APIError({"message": "No PDF templates found. Check your pdf_templates folder and filenames."})

    # Single vs ZIP
    if len(outputs) == 1 and not include_debug:
        fname, b = outputs[0]
        headers = {
            "X-Debug-Doc-Name": debug_items[0].get("doc_name","") if debug_items else "",
            "X-Debug-Template": debug_items[0].get("template_file","") if debug_items else "",
            "X-Debug-Fields": str(len(debug_items[0].get("field_names",[]))) if debug_items else "",
        }
        return {"mode": "single", "bytes": b, "filename": fname, "headers": headers}

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, b in outputs:
            zf.writestr(fname, b)
        if include_debug and debug_items:
            debug_payload = {
                "generated_at": timezone.localtime().isoformat(),
                "items": debug_items,
                "doc_request_id": doc_request_id,
            }
            req_code = (data.get("header") or {}).get("request_code", "REQ")
            zf.writestr(f"DEBUG-{req_code}.json", json.dumps(debug_payload, indent=2))

    req_code = (data.get("header") or {}).get("request_code", "REQ")
    return {"mode": "zip", "bytes": zbuf.getvalue(), "filename": f"{req_code}-documents.zip"}

def mark_released(doc_request_id: int, staff_id: Optional[int], reason: Optional[str]) -> Tuple[bool, str]:
    try:
        header, _, _, _ = get_detail_bundle(doc_request_id)
        current_status = (header.get("status") or "")
    except Exception:
        return False, "Failed to verify request status."

    norm = re.sub(r"[\s_]+", "_", current_status.strip().upper())
    if norm != "READY_FOR_PICKUP":
        return False, "Cannot mark as RELEASED. Request must be READY_FOR_PICKUP first."

    res = supabase.rpc("mark_request_released", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        return False, f"Failed: {res.error.message}"
    return True, "Marked as released."

def decline_request(doc_request_id: int, staff_id: Optional[int], reason: Optional[str]) -> Optional[str]:
    # returns None on success; error string otherwise
    return _set_status(doc_request_id, "DECLINED", staff_id, reason)

# ────────────────────────────────────────────────────────────
# AJAX data helpers
# ────────────────────────────────────────────────────────────
def fetch_purposes_by_request_type(req_doc_type_id: int) -> List[Dict[str, Any]]:
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

def search_residents_simple(q: str) -> List[Dict[str, Any]]:
    like = f"%{q}%"
    res = (
        supabase.table("person")
        .select("person_id, person_code, first_name, last_name, email")
        .or_(f"first_name.ilike.{like},last_name.ilike.{like},person_code.ilike.{like}")
        .limit(30)
        .execute()
    )
    return res.data or []

def rpc_search_person_by_key(q: str) -> List[Dict[str, Any]]:
    if len(q) < 2:
        return []
    try:
        res = supabase.rpc("search_person_by_code_or_name", {"p_key": q}).execute()
        return res.data or []
    except Exception:
        return []

def fetch_request_doc_types() -> List[Dict[str, Any]]:
    res = (
        supabase.table("request_document_type")
        .select("request_document_type_id, request_document_type_name")
        .order("request_document_type_name")
        .execute()
    )
    return res.data or []

# ────────────────────────────────────────────────────────────
# Walk-in request helpers
# ────────────────────────────────────────────────────────────
def build_walkin_payload(
    requested_by: int,
    is_on_behalf_flag: bool,
    on_behalf_of: Optional[int],
    business_id: Optional[int],
    req_doc_type_id: Optional[int],
    purpose_notes: Optional[str],
    line_document_purpose_ids: List[int],
    line_quantities: List[int],
    line_offenses: List[Optional[int]],
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Returns (ok, error_message, payload_client_shape, rpc_args)
    """
    if not requested_by:
        return False, "Please select a resident first (Requester).", None, None
    if not req_doc_type_id or not line_document_purpose_ids:
        return False, "Please choose a document and a purpose.", None, None

    # Subject
    subject_id = (on_behalf_of if (is_on_behalf_flag and on_behalf_of) else requested_by)
    is_on_behalf = bool(subject_id and requested_by and subject_id != requested_by)

    # Map doc_purpose meta
    meta_rows = { r["document_purpose_id"]: r for r in fetch_purposes_by_request_type(int(req_doc_type_id)) }

    lines: List[Dict[str, Any]] = []
    for i, dp_id in enumerate(line_document_purpose_ids):
        qty = 1
        try:
            qty = max(1, int(line_quantities[i]))
        except Exception:
            pass

        offense_no = None
        try:
            offense_no = int(line_offenses[i]) if line_offenses[i] is not None else None
        except Exception:
            offense_no = None

        meta = meta_rows.get(dp_id) or {}
        details: Dict[str, Any] = {}
        if meta.get("purpose_code"):
            details["purpose_code"] = meta["purpose_code"]
        if meta.get("default_details"):
            details.update(meta["default_details"] or {})

        lines.append({
            "document_purpose_id": dp_id,
            "quantity": qty,
            "offense_no": offense_no,
            "details": details,
        })

    # Identify doc type name and enforce BC requirements
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

    if doc_type_name.strip().upper() == BRGY_BUSINESS_DOC_NAME:
        if not business_id:
            return False, "Business is required for Barangay Business Clearance.", None, None
        bc_details = _fetch_business_clearance_fields(int(business_id), subject_id or requested_by)
        for ln in lines:
            ln["details"] = {**(ln.get("details") or {}), **bc_details}

    payload_client_shape = {
        "requested_by": requested_by,
        "on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
        "is_on_behalf": is_on_behalf,
        "business_id": business_id,
        "purpose_notes": purpose_notes,
        "lines": lines,
    }
    rpc_args = {
        "p_requested_by": requested_by,
        "p_on_behalf_of": (subject_id if (is_on_behalf and subject_id) else None),
        "p_is_on_behalf": is_on_behalf,
        "p_business_id": business_id,
        "p_purpose_notes": purpose_notes,
        "p_lines": lines,
    }
    return True, None, payload_client_shape, rpc_args

def create_document_request(rpc_args: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str]]:
    try:
        res = supabase.rpc("create_document_request", rpc_args).execute()
    except Exception as e:
        return False, None, f"RPC failed: {e}"

    if getattr(res, "error", None):
        return False, None, f"Supabase error: {res.error.message}"

    data = res.data
    new_id = None
    if isinstance(data, list) and data:
        new_id = data[0]
    elif isinstance(data, dict) and "doc_request_id" in data:
        new_id = data["doc_request_id"]
    else:
        new_id = data

    if not new_id:
        return False, None, "Could not obtain new request ID from RPC."
    return True, int(new_id), None

# ────────────────────────────────────────────────────────────
# Business registration helpers
# ────────────────────────────────────────────────────────────
def _js(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    return v

def upload_files_and_register_business(
    staff_id: int,
    owner_person_id: int,
    cleaned_data: Dict[str, Any],
    files: List[Any],
    bucket: str,
) -> Tuple[bool, Optional[str]]:
    # Upload proofs
    uploaded_paths: List[str] = []
    for f in files:
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        key = f"business-proofs/{timezone.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.{ext}"
        try:
            supabase.storage.from_(bucket).upload(key, f.read(), {"content-type": f.content_type})
            uploaded_paths.append(key)
        except Exception as e:
            return False, f"Failed to upload proof '{f.name}': {e}"

    # Coerce/prepare payload
    btype_id   = int(cleaned_data["b_type"])         if cleaned_data.get("b_type") else None
    own_id     = int(cleaned_data["ownership_type"]) if cleaned_data.get("ownership_type") else None
    day_start  = int(cleaned_data["opt_days_start"]) if cleaned_data.get("opt_days_start") else None
    day_end    = int(cleaned_data["opt_days_end"])   if cleaned_data.get("opt_days_end") else None
    has_clearance = (cleaned_data.get("prev_clearance") == "yes")

    payload = {
        "p_performer_staff_id": int(staff_id),
        "p_owner_person_id": int(owner_person_id),

        "p_business_name": cleaned_data.get("b_name"),
        "p_business_location_desc": cleaned_data.get("b_desc"),
        "p_business_nature": cleaned_data.get("b_nature"),

        "p_prev_yr_total_gross_sales": _js(cleaned_data.get("prevgross")),
        "p_date_est": _js(cleaned_data.get("date_est")),
        "p_dti_sec_reg_num": cleaned_data.get("dti"),
        "p_capital_invested": _js(cleaned_data.get("capital_invested")),
        "p_mnthly_gross_incom_est": _js(cleaned_data.get("inc_est")),
        "p_num_of_emp": cleaned_data.get("emp_num"),
        "p_has_business_clearance": has_clearance,

        "p_business_type_id": btype_id,
        "p_ownership_type_id": own_id,

        "p_operating_day_start": day_start,
        "p_operating_day_end": day_end,
        "p_operating_hour_start": _js(cleaned_data.get("opt_start")),
        "p_operating_hour_end": _js(cleaned_data.get("opt_end")),

        "p_business_latitude": _js(cleaned_data.get("latitude")),
        "p_business_longitude": _js(cleaned_data.get("longitude")),
        "p_business_city": cleaned_data.get("city"),
        "p_business_barangay": cleaned_data.get("barangay"),
        "p_business_street": cleaned_data.get("street"),
        "p_business_purok_sitio_name": cleaned_data.get("purok_sitio"),

        "p_business_proof_files": uploaded_paths or None,
    }

    try:
        resp = supabase.rpc("register_business_and_owner", payload).execute()
    except APIError as e:
        detail = getattr(e, "message", None) or str(e)
        return False, f"RPC error: {detail}"

    if getattr(resp, "error", None):
        detail = resp.error.message
        code = getattr(resp.error, "code", "") or ""
        if "P6057" in code or "P6057" in detail:
            return False, "Invalid business type. Please pick a valid type."
        if "P6058" in code or "P6058" in detail:
            return False, "Invalid ownership type. Please pick a valid type."
        if "P6061" in code or "P6061" in detail:
            return False, "Invalid operating day range. Start must be ≤ End within 1..7."
        if "P6062" in code or "P6062" in detail:
            return False, "Invalid operating hour range. Start time must be before end time."
        if "P6065" in code or "P6065" in detail:
            return False, "Missing link type 'BUSINESS PROFILING'. Contact admin."
        return False, f"RPC error: {detail}"

    return True, None

# ────────────────────────────────────────────────────────────
# Business read helpers
# ────────────────────────────────────────────────────────────
def get_business_summary() -> List[Dict[str, Any]]:
    resp = supabase.rpc("get_business_summary", {}).execute()
    return resp.data or []

def get_business_details(b_id: int) -> Dict[str, Any]:
    b_resp = supabase.rpc("get_business_details", {"p_business_id": b_id}).execute()
    b_rows = b_resp.data or []
    if not b_rows:
        raise APIError({"message": f"Business {b_id} not found."})
    b = b_rows[0]
    raw_days = str(b.get("operating_days") or "").strip()
    operating_days_list = [d.strip() for d in raw_days.split(",") if d.strip()] if raw_days else []
    b["operating_days_list"] = operating_days_list
    return b

def get_person_details(person_id: int) -> Optional[Dict[str, Any]]:
    p_resp = supabase.rpc("get_details", {"p_person_id": int(person_id)}).execute()
    p_rows = p_resp.data or []
    return p_rows[0] if p_rows else None
