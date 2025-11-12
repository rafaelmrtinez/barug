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

# BUSINESS RENEWAL
def accept_renewal_payment(
    renewal_request_id: int,
    method_id: int,
    amount_paid: float,  # kept for signature compatibility; not sent (RPC computes due)
    staff_id: int,
    or_number: str | None = None,
    paid_on: str | None = None,
    rpc_name: str = "treasurer_accept_renewal_payment_h",
) -> int:
    """
    Calls the renewal payment RPC. The SQL signature is:
        (p_renewal_request_id int,
         p_payment_method_id int,
         p_received_by_staff_id int,
         p_paid_on date/timestamptz default null,
         p_or_number text default null)

    Notes:
    - We *always* include all five params. None is allowed for the optional ones.
    - RPC returns either an int or an object/list containing 'clearance_rec_id'.
    """

    # Normalize paid_on to ISO if a datetime/date object is passed
    try:
        from datetime import date, datetime
        if isinstance(paid_on, (datetime, date)):
            paid_on = paid_on.isoformat()
    except Exception:
        pass

    payload = {
        "p_renewal_request_id": int(renewal_request_id),
        "p_payment_method_id": int(method_id),
        "p_received_by_staff_id": int(staff_id),
        "p_paid_on": paid_on,       # may be None; SQL has default
        "p_or_number": or_number,   # may be None; SQL has default
    }

    res = supabase.rpc(rpc_name, payload).execute()

    # Bubble up clear errors with context
    if getattr(res, "error", None):
        msg = getattr(res.error, "message", str(res.error))
        raise RuntimeError(f"Renewal payment failed (RPC {rpc_name}): {msg}")

    # The RPC may return one of:
    #  - an int (clearance id)
    #  - a dict with 'clearance_rec_id'
    #  - a 1-row list with that dict
    data = getattr(res, "data", None)

    def _to_int(x):
        try:
            return int(x)
        except Exception:
            return None

    if isinstance(data, int):
        cid = _to_int(data)
        if cid is not None:
            return cid

    if isinstance(data, str):
        cid = _to_int(data)
        if cid is not None:
            return cid

    if isinstance(data, dict):
        cid = _to_int(data.get("clearance_rec_id"))
        if cid is not None:
            return cid

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            cid = _to_int(first.get("clearance_rec_id"))
            if cid is not None:
                return cid
        else:
            cid = _to_int(first)
            if cid is not None:
                return cid

    # If we reach here, the RPC returned an unexpected shape
    raise RuntimeError(f"Renewal payment RPC ({rpc_name}) returned unexpected payload: {data!r}")

def accept_all_unpaid_payments(
    business_id: int,
    period_type: str,            # 'ANNUAL' or 'QUARTERLY'
    period_year: int,            # accept up to & including this year
    method_id: int,
    staff_id: int,
    paid_on: str | None = None,  # ISO date/time or None
    rpc_name: str = "treasurer_accept_all_unpaid_h",
) -> dict:
    """
    Calls the bulk-accept RPC that loops through all pending renewal requests
    (for the business, up to period_year) and accepts them one by one.

    Returns a dict like:
      {
        'processed_count': int,
        'sum_quoted_total': decimal-like,
        'items': [
           {'renewal_request_id': int, 'clearance_rec_id': int, 'quoted_total': decimal-like},
           ...
        ]
      }
    """

    # Normalize paid_on if a date/datetime was passed
    try:
        from datetime import date, datetime
        if isinstance(paid_on, (datetime, date)):
            paid_on = paid_on.isoformat()
    except Exception:
        pass

    payload = {
        "p_business_id": int(business_id),
        "p_period_type": str(period_type).upper(),
        "p_period_year": int(period_year),
        "p_payment_method_id": int(method_id),
        "p_received_by_staff_id": int(staff_id),
        "p_paid_on": paid_on,  # may be None
    }

    res = supabase.rpc(rpc_name, payload).execute()

    if getattr(res, "error", None):
        msg = getattr(res.error, "message", str(res.error))
        raise RuntimeError(f"Bulk renewal payment failed (RPC {rpc_name}): {msg}")

    data = getattr(res, "data", None)

    # Supabase can return a dict or a 1-row list with a dict
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]

    # Fallback: unexpected shape
    raise RuntimeError(f"Bulk renewal RPC ({rpc_name}) returned unexpected payload: {data!r}")

def mark_for_printing(doc_request_id: int, staff_id: int, reason: str | None = None) -> None:
    res = supabase.rpc("mark_request_for_printing", {
        "p_doc_request_id": doc_request_id,
        "p_staff_id": staff_id,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Mark for printing failed"))

# treasurer/services/payments_service.py
def confirm_and_post_or(doc_request_id: int, staff_id: int, or_number: str | None = None, payment_method_id: int = 5) -> int:
    """
    Calls treasurer_confirm_and_post_or RPC:
      - re/uses OR if exists, else inserts
      - logs PAYMENT_ACCEPTED
      - sets status → PAID (if needed) → FOR_PRINTING
    Returns the OR ID.
    """
    res = supabase.rpc("treasurer_confirm_and_post_or", {
        "p_doc_request_id": int(doc_request_id),
        "p_staff_id": int(staff_id),
        "p_or_number": or_number,          # can be None → auto-generate
        "p_payment_method_id": int(payment_method_id),  # default 5 = Online GCash
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Confirm & Post OR failed"))
    return int(res.data)
