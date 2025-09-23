from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, date
from django.utils import timezone
from authentication.supabase_client import supabase

def pick(*vals, allow_zero: bool = False):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip() == "":
                continue
            if v.strip() == "0" and not allow_zero:
                continue
            return v
        if v == 0 and not allow_zero:
            continue
        return v
    return None

def _to_date(val) -> date | None:
    if not val:
        return None
    try:
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if "T" in s:
            s = s.split("T", 1)[0]
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _calc_age_from_birthdate(bday_val) -> int | None:
    bday = _to_date(bday_val)
    if not bday: return None
    today = timezone.localdate()
    age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
    return max(age, 0)

def subject_view(header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, Any]:
    has_on_behalf = bool(header.get("on_behalf_of_person_id") or header.get("on_behalf_full_name"))

    full_name = pick(
        line.get("subject_full_name"),
        header.get("subject_full_name"),
        header.get("on_behalf_full_name") if has_on_behalf else header.get("requester_full_name"),
        header.get("requester_full_name"),
        header.get("resident_name"),
        header.get("full_name"),
    )

    address = pick(
        line.get("subject_address"),
        header.get("subject_address"),
        header.get("on_behalf_address") if has_on_behalf else header.get("address"),
        header.get("address"),
    )

    age = pick(
        line.get("subject_age"),
        header.get("subject_age"),
        header.get("on_behalf_age") if has_on_behalf else header.get("requester_age"),
        header.get("requester_age"),
        header.get("age"),
        allow_zero=True,
    )

    need_age_from_bday = (age is None or str(age).strip() == "" or str(age) == "0")
    if need_age_from_bday:
        bday = pick(
            line.get("subject_birthdate"),
            header.get("subject_birthdate"),
            header.get("on_behalf_birthdate") if has_on_behalf else header.get("requester_birthdate"),
            header.get("birthdate"),
        )
        if not bday and has_on_behalf and header.get("on_behalf_of_person_id"):
            try:
                p = supabase.table("person").select("birthdate").eq(
                    "person_id", header["on_behalf_of_person_id"]
                ).single().execute()
                if getattr(p, "data", None):
                    bday = (p.data or {}).get("birthdate")
            except Exception:
                pass
        got = _calc_age_from_birthdate(bday)
        if got is not None:
            age = got

    civil = pick(
        line.get("subject_civil_status"),
        header.get("subject_civil_status"),
        header.get("on_behalf_civil_status") if has_on_behalf else header.get("civil_status"),
        header.get("civil_status"),
    )

    nat = pick(
        line.get("subject_nationality"),
        header.get("subject_nationality"),
        header.get("on_behalf_nationality") if has_on_behalf else header.get("nationality"),
        header.get("nationality"),
    )

    return {
        "full_name": full_name or "",
        "address": address or "",
        "age": age if age is not None else "",
        "civil_status": civil or "",
        "nationality": nat or "",
        "is_on_behalf": has_on_behalf,
    }
