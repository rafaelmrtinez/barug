# treasurer/services/fees_service.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from authentication.supabase_client import supabase

# Django utilities are used only for formatting/display.
# If this module is used outside Django, you can remove django imports
# and implement simple formatting instead.
try:
    from django.utils import timezone
    from django.utils.formats import date_format, time_format
    _HAS_DJANGO = True
except Exception:
    timezone = None  # type: ignore
    date_format = None  # type: ignore
    time_format = None  # type: ignore
    _HAS_DJANGO = False


# ---------- RPC wrappers (existing) ----------

def search_fee_items(q: Optional[str]) -> List[Dict[str, Any]]:
    """Call RPC search_fee_items and return list of dicts."""
    res = supabase.rpc("search_fee_items", {"p_query": q}).execute()
    return getattr(res, "data", None) or []


def recent_fee_changes(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Call RPC get_recent_fee_changes and return raw rows.
    Use get_fee_timeline_formatted() to get formatted rows for templates.
    """
    res = supabase.rpc("get_recent_fee_changes", {"p_limit": limit}).execute()
    return getattr(res, "data", None) or []


def update_fee_amount(fee_code: str, new_amount: float, staff_id: int, reason: Optional[str]):
    """Call RPC to update fee amount. Raises RuntimeError when RPC returns error."""
    res = supabase.rpc("treasurer_update_fee_amount", {
        "p_changed_by_staff_id": staff_id,
        "p_fee_code": fee_code,
        "p_new_amount": new_amount,
        "p_reason": reason,
    }).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Update failed"))


def add_fee(payload: Dict[str, Any]):
    """Call RPC to add a new fee. Raises RuntimeError on failure."""
    res = supabase.rpc("treasurer_add_fee", payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Add fee failed"))


def fetch_fee_full(fee_code: str) -> Dict[str, Any]:
    """Return detailed fee record from RPC treasurer.fetch_fee_full (or similar)."""
    res = supabase.rpc("fetch_fee_full", {"p_fee_code": fee_code}).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Fetch failed"))
    # RPC returns array-of-rows; we prefer the first row or empty dict
    data = getattr(res, "data", None) or []
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}


def list_document_types() -> List[Dict[str, Any]]:
    """Return a list of document types (raw RPC result)."""
    res = supabase.rpc("get_document_types", {}).execute()
    return getattr(res, "data", None) or []


def upsert_fee(payload: Dict[str, Any]):
    """Insert or update a fee via RPC; raises on error."""
    res = supabase.rpc("treasurer_upsert_fee", payload).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "Upsert failed"))


def list_fee_document_types() -> List[Dict[str, Any]]:
    """Return list of fee document types for the level-1 page."""
    return getattr(supabase.rpc("list_fee_document_types", {}).execute(), "data", None) or []


def search_fee_items_by_doc_type_id(doc_type_id: int, q: Optional[str]) -> List[Dict[str, Any]]:
    """Return fees filtered by document type id and optional query."""
    res = supabase.rpc("search_fee_items_by_doc_type_id", {
        "p_doc_type_id": doc_type_id,
        "p_query": q
    }).execute()
    return getattr(res, "data", None) or []


def get_fee_timeline(fee_code: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Return raw timeline rows for a fee from RPC get_fee_timeline.
    Expected to return rows containing timestamps, old/new amounts, changed_by, reason, etc.
    """
    res = supabase.rpc("get_fee_timeline", {"p_fee_code": fee_code, "p_limit": limit}).execute()
    if getattr(res, "error", None):
        return []
    return getattr(res, "data", None) or []


# ---------- Helpers: parse + format timeline rows for templates ----------

def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Best-effort parse a datetime value returned from Supabase.
    Supabase may return ISO8601 strings or Python datetimes depending on client.
    Returns a naive or tz-aware datetime (depending on input) or None.
    """
    if value is None:
        return None
    # If already a datetime object
    if isinstance(value, datetime):
        return value

    # If it's a string, attempt to parse ISO variants
    if isinstance(value, str):
        s = value.strip()
        # Strip trailing Z for fromisoformat (keeps offset-aware forms)
        if s.endswith("Z"):
            s = s[:-1]
        # Try fromisoformat
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass

        # Fallback: try common formats
        fmts = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for f in fmts:
            try:
                return datetime.strptime(s, f)
            except Exception:
                continue
    # Unknown type
    return None


def _localize_and_format(dt: Optional[datetime]) -> Dict[str, str]:
    """
    Given a datetime (possibly naive or tz-aware), return:
      - pill: MM-DD (string)
      - pretty: e.g. "Oct 26, 2025 • 05:39 PM"
    Uses Django's date_format/time_format when available, otherwise falls back to strftime.
    """
    if not dt:
        return {"pill": "", "pretty": ""}

    # If Django timezone utilities are available, convert to localtime when possible
    if _HAS_DJANGO and timezone is not None:
        try:
            # If dt is naive, timezone.localtime will raise; guard with timezone.is_aware
            if dt.tzinfo is None:
                # assume UTC for naive datetimes returned as strings by Supabase
                # this is a best-effort assumption and can be adjusted if your DB uses local timestamps
                import pytz  # optional dependency; only used when Django present
                dt = dt.replace(tzinfo=pytz.UTC)
            dt_local = timezone.localtime(dt)
        except Exception:
            dt_local = dt
        try:
            pill = dt_local.strftime("%m-%d")
            # date_format/time_format are locale-aware; fallback if missing
            pretty_date = date_format(dt_local, "M j, Y") if date_format else dt_local.strftime("%b %d, %Y")
            pretty_time = time_format(dt_local, "P") if time_format else dt_local.strftime("%I:%M %p")
            pretty = f"{pretty_date} • {pretty_time}"
            return {"pill": pill, "pretty": pretty}
        except Exception:
            # final fallback
            return {"pill": dt_local.strftime("%m-%d"), "pretty": dt_local.strftime("%b %d, %Y • %I:%M %p")}
    else:
        # No Django: use stdlib formatting (assume dt is naive or already local)
        try:
            pill = dt.strftime("%m-%d")
            pretty = dt.strftime("%b %d, %Y • %I:%M %p")
            return {"pill": pill, "pretty": pretty}
        except Exception:
            return {"pill": "", "pretty": ""}


def _format_timeline_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize and format raw timeline rows returned by Supabase RPCs for template usage.

    Output dict keys:
      - fee_code
      - changed_at (datetime or None)
      - changed_at_pill (e.g., "10-30")
      - changed_at_pretty (e.g., "Oct 26, 2025 • 05:39 PM")
      - old_amount (numeric)
      - new_amount (numeric)
      - changed_by (string)
      - reason (string)
    """
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        # Field extraction - tolerant to different RPC shapes
        fee_code = (
            r.get("fee_code")
            or r.get("fee__fee_code")
            or r.get("fee")
            or r.get("code")
            or r.get("fee_code_text")
            or ""
        )

        # changed_at could be named differently, try a few variants
        raw_dt = (
            r.get("changed_at")
            or r.get("created_at")
            or r.get("timestamp")
            or r.get("changed_at_utc")
            or r.get("occurred_at")
        )

        dt = _parse_datetime(raw_dt)
        fmt = _localize_and_format(dt)

        # Amount extraction
        old_amount = r.get("old_amount") or r.get("previous_amount") or r.get("from_amount") or r.get("amount_before") or 0
        new_amount = r.get("new_amount") or r.get("amount") or r.get("to_amount") or r.get("amount_after") or 0

        # Changed by
        changer = (
            r.get("changed_by_name")
            or r.get("changed_by_fullname")
            or r.get("changed_by")
            or r.get("changed_by_username")
            or r.get("user")
            or r.get("author")
            or ""
        )

        reason = (r.get("reason") or r.get("note") or r.get("remarks") or "").strip()

        out.append({
            "fee_code": fee_code,
            "changed_at": dt,
            "changed_at_pill": fmt["pill"],
            "changed_at_pretty": fmt["pretty"],
            "old_amount": old_amount,
            "new_amount": new_amount,
            "changed_by": changer,
            "reason": reason,
        })

    return out


# ---------- Convenience wrapper returning formatted timeline ----------

def get_fee_timeline_formatted(fee_code: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch raw timeline rows for fee_code and return formatted rows ready for templates.
    """
    raw = get_fee_timeline(fee_code, limit=limit) or []
    return _format_timeline_rows(raw)


# If you prefer to keep the old function name `get_fee_timeline` returning formatted rows,
# uncomment the following alias and comment out the raw-get above:
# get_fee_timeline = get_fee_timeline_formatted
