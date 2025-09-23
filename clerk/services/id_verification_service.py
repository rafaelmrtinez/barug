from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from django.utils import timezone
from postgrest.exceptions import APIError

# Map statuses → Bootstrap badge classes
ID_STATUS_UI: Dict[str, str] = {
    "PENDING": "badge bg-warning-subtle text-warning-emphasis",
    "APPROVED": "badge bg-success-subtle text-success-emphasis",
    "REJECTED": "badge bg-danger-subtle text-danger-emphasis",
    "DECLINED": "badge bg-danger-subtle text-danger-emphasis",
    "RETURNED_FOR_CORRECTION": "badge bg-info-subtle text-info-emphasis",
}

def _fmt_ts_local(val: Any) -> str:
    if not val:
        return "—"
    try:
        # Accept naive/ISO strings or datetimes; coerce Z to UTC
        if isinstance(val, str):
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        else:
            dt = val
        return timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return str(val)

def _full_name(r: Dict[str, Any]) -> str:
    # Prefer explicit prebuilt name, else requester_*, else generic first/last
    nm = (r.get("requester_full_name") or "").strip()
    if nm:
        return nm
    fn = (r.get("requester_first_name") or r.get("first_name") or "").strip()
    mn = (r.get("requester_middle_name") or r.get("middle_name") or "").strip()
    ln = (r.get("requester_last_name") or r.get("last_name") or "").strip()
    suf = (r.get("requester_suffix") or r.get("suffix") or "").strip()
    mi = (mn[:1] + ". ") if mn else ""
    return (f"{fn} {mi}{ln} {suf}").strip() or "—"

def _status_fields(r: Dict[str, Any]) -> tuple[str, str]:
    raw = (r.get("latest_status") or r.get("request_status") or "PENDING")
    st = raw.strip().upper().replace(" ", "_")
    text = st.replace("_", " ").title()
    cls = ID_STATUS_UI.get(st, "badge text-bg-secondary")
    return text, cls

def _submitted_ts(r: Dict[str, Any]) -> Any:
    # Support several column names
    return r.get("date_requested") or r.get("validation_date") or r.get("request_date") or r.get("created_at")

def normalize_verification_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for r in rows:
        r["requester_display"] = _full_name(r)
        r["submitted_fmt"] = _fmt_ts_local(_submitted_ts(r))
        text, cls = _status_fields(r)
        r["status_text"], r["status_cls"] = text, cls
    # Sort newest first
    def _key(x: Dict[str, Any]):
        val = _submitted_ts(x)
        try:
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            return val or datetime.min
        except Exception:
            return datetime.min
    rows.sort(key=_key, reverse=True)
    return rows

def fetch_id_verification_requests(supabase, search: str = "") -> List[Dict[str, Any]]:
    """Fetch ALL verification requests via Supabase RPC and (optionally) filter by search."""
    try:
        resp = supabase.rpc("get_id_validation_requests", {}).execute()
        rows: List[Dict[str, Any]] = resp.data or []
    except APIError:
        return []
    normalize_verification_rows(rows)
    if search:
        q = search.lower()
        def _match(x: Dict[str, Any]) -> bool:
            hay = " ".join([
                x.get("requester_display", ""),
                x.get("latest_status", "") or x.get("request_status", "") or "",
            ]).lower()
            return q in hay
        rows = [r for r in rows if _match(r)]
    return rows

def get_verification_status_for_person(supabase, person_id: int) -> Optional[Dict[str, Any]]:
    """Find the latest status row for a person (by requester_person_id)."""
    rows = fetch_id_verification_requests(supabase, search="")
    for r in rows:
        if r.get("requester_person_id") == person_id:
            return r
    return None
