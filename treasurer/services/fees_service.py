from __future__ import annotations
from typing import Any, Dict, List
from authentication.supabase_client import supabase

def search_fee_items(q: str | None) -> List[Dict[str, Any]]:
    res = supabase.rpc("search_fee_items", {"p_query": q}).execute()
    return res.data or []

def recent_fee_changes(limit: int = 50) -> List[Dict[str, Any]]:
    res = supabase.rpc("get_recent_fee_changes", {"p_limit": limit}).execute()
    return res.data or []

def update_fee_amount(fee_code: str, new_amount: float, staff_id: int, reason: str | None):
    res = supabase.rpc("treasurer_update_fee_amount", {
        "p_changed_by_staff_id": staff_id,
        "p_fee_code": fee_code,
        "p_new_amount": new_amount,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Update failed"))

def add_fee(payload: Dict[str, Any]):
    res = supabase.rpc("treasurer_add_fee", payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Add fee failed"))

def fetch_fee_full(fee_code: str) -> Dict[str, Any]:
    res = supabase.rpc("fetch_fee_full", {"p_fee_code": fee_code}).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Fetch failed"))
    return res.data or {}

def list_document_types() -> List[Dict[str, Any]]:
    res = supabase.rpc("get_document_types", {}).execute()
    return res.data or []

def upsert_fee(payload: Dict[str, Any]):
    res = supabase.rpc("treasurer_upsert_fee", payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Upsert failed"))
