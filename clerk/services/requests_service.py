from __future__ import annotations

from typing import Any, Dict, Optional
from postgrest.exceptions import APIError
from authentication.supabase_client import supabase


# ───────────────────────────────────── RPC helpers ─────────────────────────────────────

def _rpc(name: str, payload: Dict[str, Any]) -> Optional[str]:
    """Call an RPC and return an error message if any; otherwise None."""
    res = supabase.rpc(name, payload).execute()
    if getattr(res, "error", None):
        return res.error.message
    return None


# ──────────────────────────────────── Public API ───────────────────────────────────────

def _fetch_bundle(doc_request_id: int) -> Dict[str, Any]:
    """
    Returns the request detail bundle for the clerk detail page.
    RPC: fetch_doc_request_detail_bundle(p_doc_request_id int)
    """
    res = supabase.rpc(
        "fetch_doc_request_detail_bundle",
        {"p_doc_request_id": doc_request_id},
    ).execute()
    if getattr(res, "error", None):
        raise APIError({"message": res.error.message})

    data = res.data or {}
    if isinstance(data, list) and data:
        data = data[0]
    return data


def _set_status(
    doc_request_id: int,
    status: str,
    staff_id: Optional[int],
    reason: Optional[str] = None,
) -> Optional[str]:
    """
    Single, audited status setter that ALWAYS goes through:
      set_request_status(p_doc_request_id, p_status_name, p_actor_staff_id, p_details jsonb)

    Using this ensures the timeline actor is STAFF (not SYSTEM).
    """
    if not staff_id:
        return "Missing staff id."

    status_norm = (status or "").strip().upper().replace(" ", "_")
    details = {"reason": reason} if reason else {}
    payload = {
        "p_doc_request_id": doc_request_id,
        "p_status_name": status_norm,
        "p_actor_staff_id": int(staff_id),
        "p_details": details,
    }
    return _rpc("set_request_status", payload)


# Convenience wrappers used by your views (they all route to _set_status)

def confirm_and_send_to_printing(
    doc_request_id: int,
    staff_id: int,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Clerk presses 'Confirm & Send to Printing' (paid path) → FOR_PRINTING."""
    return _set_status(doc_request_id, "FOR_PRINTING", staff_id, notes)


def confirm_forward_treasurer(
    doc_request_id: int,
    staff_id: int,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Clerk presses 'Confirm & Forward to Treasurer' (unpaid path) → FOR_TREASURER_REVIEW."""
    return _set_status(doc_request_id, "FOR_TREASURER_REVIEW", staff_id, notes)


def ready_for_pickup(
    doc_request_id: int,
    staff_id: int,
    reason: Optional[str] = None,
) -> Optional[str]:
    """Marks the request READY FOR PICKUP."""
    return _set_status(doc_request_id, "READY FOR PICKUP", staff_id, reason)


def release_request(
    doc_request_id: int,
    staff_id: int,
    reason: Optional[str] = None,
) -> Optional[str]:
    """Marks the request RELEASED."""
    return _set_status(doc_request_id, "RELEASED", staff_id, reason)
