from __future__ import annotations
from typing import Any, Dict
from postgrest.exceptions import APIError
from authentication.supabase_client import supabase

def _fetch_bundle(doc_request_id: int) -> Dict[str, Any]:
    res = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(res, "error", None):
        raise APIError({"message": res.error.message})
    return res.data or {}

def _set_status(doc_request_id: int, status: str, staff_id: int | None, reason: str | None = None) -> str | None:
    if not staff_id:
        return "Missing staff id."
    # (kept your existing RPC; adjust if you route by status)
    res = supabase.rpc(
        "forward_to_clerk_for_printing",
        {"p_doc_request_id": doc_request_id, "p_staff_id": staff_id, "p_reason": reason},
    ).execute()
    return getattr(res, "error", None) and res.error.message
