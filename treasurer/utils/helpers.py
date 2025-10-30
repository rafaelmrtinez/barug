# treasurer/utils/helpers.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import HttpRequest

PH_TZ = ZoneInfo("Asia/Manila")


def _staff_id(request: HttpRequest) -> int | None:
    """
    Prefer the staff_id we stash in session; fallback to request.profile.
    (Identical to the inline version.)
    """
    auth = request.session.get("auth") or {}
    sid = auth.get("staff_id")
    if sid:
        return sid
    prof = getattr(request, "profile", None) or getattr(request, "person_profile", None)
    return getattr(prof, "staff_id", None)


def _fmt_occured_at(val) -> str:
    """
    Accepts a datetime or ISO string, returns a Manila-local formatted string.
    (Identical to the inline version.)
    """
    if not val:
        return "—"
    dt = None
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, str):
        dt = parse_datetime(val)
    if not dt:
        return str(val)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    dt_local = timezone.localtime(dt, PH_TZ)
    return dt_local.strftime("%b %d, %Y • %I:%M %p")


def _resolve_actor_name(ev: Dict[str, Any], header: Dict[str, Any]) -> str:
    """
    Return a friendly actor name for a timeline event.
    (Identical to the inline version.)
    """
    for k in ("staff_name", "resident_name"):
        v = (ev.get(k) or "").strip()
        if v:
            return v
    actor = (ev.get("actor") or "").strip()
    if actor:
        if actor.isdigit() and header.get("requester_full_name"):
            return header["requester_full_name"]
        return actor
    ut = (ev.get("user_type_name") or "").strip().upper()
    if ut == "PERSON" and header.get("requester_full_name"):
        return header["requester_full_name"]
    return "SYSTEM"


def _extract_payment_method_label(payments: Dict[str, Any], timeline: List[Dict[str, Any]]) -> str | None:
    """
    Find a human label for the payment method.
    (Identical to the inline version.)
    """
    for k in ("latest_method_name", "latest_payment_method", "latest_method", "method_name"):
        v = (payments or {}).get(k)
        if v:
            return str(v)
    for e in reversed(timeline or []):
        d = e.get("details") or {}
        if d.get("payment_method"):
            return str(d["payment_method"])
    return None


def build_page_numbers(curr: int, total: int, radius: int = 2) -> List[int | None]:
    """
    Build a compact pagination list with ellipses as None.
    (Identical to the repeated inline version.)
    """
    if total <= 1:
        return [1]
    nums: List[int | None] = []
    left = max(1, curr - radius)
    right = min(total, curr + radius)
    if left > 1:
        nums.append(1)
        if left > 2:
            nums.append(None)
    nums.extend(range(left, right + 1))
    if right < total:
        if right < total - 1:
            nums.append(None)
        nums.append(total)
    return nums


def split_name_main_sub(name: str) -> Tuple[str, str | None]:
    """
    Split a display name into main/sub using the same separators and rules you used in fees().
    Returns (main, sub) with exact same behavior.
    """
    name = (name or "").strip()
    main, sub = name, None
    for sep in [" – ", " — ", " - "]:
        if sep in name:
            parts = [p.strip() for p in name.split(sep, 1)]
            if len(parts) == 2:
                main, sub = parts[0], parts[1]
            break
    return main, sub
