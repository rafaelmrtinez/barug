from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from authentication.supabase_client import supabase

BRGY_BUSINESS_DOC_NAME = "BARANGAY BUSINESS CLEARANCE"
BRGY_BUSINESS_PDF_FILE = "barangay-business-clearance.pdf"

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

def fetch_business_clearance_fields(business_id: int, subject_person_id: Optional[int]) -> Dict[str, Any]:
    """
    Pull business + address + subject basics and return semantic keys
    expected by the Business Clearance PDF (pre-mapping).
    """
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

    addr = b.get("address") or {}
    purok = (((addr.get("purok_sitio") or {}) or {}).get("purok_sitio_name")) or ""
    parts = [addr.get("street"), purok, addr.get("barangay"), addr.get("city")]
    business_address = ", ".join([str(p).strip() for p in parts if p])

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
    print("[WALKIN DEBUG] derived Business Clearance details:", details)
    return details

def fetch_request_doc_types() -> List[Dict[str, Any]]:
    res = (
        supabase.table("request_document_type")
        .select("request_document_type_id, request_document_type_name")
        .order("request_document_type_name")
        .execute()
    )
    return res.data or []

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

def get_doc_type_name(req_doc_type_id: int) -> str:
    try:
        dt_row = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .eq("request_document_type_id", req_doc_type_id)
            .limit(1)
            .execute()
        )
        return (((dt_row.data or [{}])[0]) or {}).get("request_document_type_name") or ""
    except Exception:
        return ""

def search_residents_for_walkin(q: str) -> List[Dict[str, Any]]:
    like = f"%{q}%"
    res = (
        supabase.table("person")
        .select("person_id, person_code, first_name, last_name, email")
        .or_(f"first_name.ilike.{like},last_name.ilike.{like},person_code.ilike.{like}")
        .limit(30)
        .execute()
    )
    return res.data or []
