# resident/services.py
from typing import Any, Dict, List, Optional, Tuple
from authentication.supabase_client import supabase

Peso = str  # we format on server for templates

def peso(amount: Any) -> Peso:
    try:
        return f"₱{float(amount):,.2f}"
    except Exception:
        return "₱0.00"

def fetch_request_list(
    person_id: int,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Reads from a view tailored for web list.
    Fallback to v_doc_request_list if you don't have the web view yet.
    """
    tbl = "v_doc_request_list_web"  # see SQL at bottom. Or use "v_doc_request_list"
    qy = supabase.table(tbl).select("*").eq("requested_by_person_id", person_id)

    if status and status.upper() != "ALL":
        qy = qy.eq("status", status)

    if q:
        # PostgREST or() filter (matches request code, doc name, purpose)
        ilike = f".ilike.%{q}%"
        qy = qy.or_(
            "request_code" + ilike + ",document_type_name" + ilike + ",purpose_label" + ilike
        )

    qy = qy.order("created_at", desc=True).limit(limit)
    return qy.execute().data or []

def fetch_request_detail_bundle(doc_request_id: int) -> Dict[str, Any]:
    """
    Returns header, lines, payments, timeline in one dict for the detail page.
    Uses views when possible.
    """
    header = supabase.table("v_doc_request_list_web").select("*").eq("doc_request_id", doc_request_id).single().execute().data
    if not header:
        # fallback if the web view doesn't exist
        header = supabase.table("v_doc_request_list").select("*").eq("doc_request_id", doc_request_id).single().execute().data

    lines = supabase.table("v_doc_request_detail").select("*").eq("doc_request_id", doc_request_id).order("doc_request_line_id", desc=False).execute().data or []

    payments = supabase.table("official_receipt").select("or_number, amount_paid, created_at").eq("doc_request_id", doc_request_id).order("created_at", desc=True).execute().data or []

    timeline = supabase.table("v_document_timeline").select("*").eq("doc_request_id", doc_request_id).order("happened_at", desc=True).execute().data or []

    # prettify a little for template
    total_due = header.get("amount_due", 0) if header else 0
    latest_or = payments[0] if payments else None

    return {
        "header": header,
        "lines": lines,
        "payments": payments,
        "timeline": timeline,
        "pretty": {
            "amount_due_peso": peso(total_due),
            "or_count": len(payments),
            "latest_or": latest_or,
        },
    }
