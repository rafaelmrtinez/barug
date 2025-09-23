from __future__ import annotations
from typing import Any, Dict, List
from authentication.supabase_client import supabase

def list_payment_methods() -> List[Dict[str, Any]]:
    pm_res = supabase.rpc("get_payment_methods", {}).execute()
    return pm_res.data or []

def accept_payment(doc_request_id: int, method_id: int, amount_paid: float, staff_id: int) -> int:
    res = supabase.rpc("treasurer_accept_payment", {
        "p_amount_paid": amount_paid,
        "p_doc_request_id": doc_request_id,
        "p_payment_method_id": method_id,
        "p_received_by_staff_id": staff_id,
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Payment failed"))
    return int(res.data)

def mark_for_printing(doc_request_id: int, staff_id: int, reason: str | None = None) -> None:
    res = supabase.rpc("mark_request_for_printing", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Mark for printing failed"))
