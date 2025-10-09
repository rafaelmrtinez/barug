from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from authentication.supabase_client import supabase

def build_fullname(r: Dict) -> str:
    ln = (r.get("last_name") or "").strip()
    fn = (r.get("first_name") or "").strip()
    mn = (r.get("middle_name") or "").strip()
    sx = (r.get("suffix") or "").strip()
    mid = f" {mn}" if mn else ""
    suf = f" {sx}" if sx else ""
    # Keep original casing; your UI can uppercase with CSS if needed
    return f"{ln}, {fn}{mid}{suf}".strip()

def list_residents_minimal(
    search: str = "",
    page: int = 1,
    page_size: int = 15
) -> Tuple[List[Dict], int]:
    """
    Bullet-proof minimal list from Supabase (no nested joins):
      returns rows: [{person_id, fullname, address:'—'}], total
    """
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    from_idx = (page - 1) * page_size
    to_idx = from_idx + page_size - 1

    # Ask Supabase for an exact count so paginator works
    q = supabase.table("person").select(
        "person_id,last_name,first_name,middle_name,suffix",
        count="exact"
    )

    if search:
        like = f"%{search}%"
        # PostgREST OR filter – this form is the most forgiving
        q = q.or_(
            f"last_name.ilike.{like},first_name.ilike.{like},middle_name.ilike.{like},suffix.ilike.{like}"
        )

    # Order + page
    q = q.order("last_name", desc=False).order("first_name", desc=False).range(from_idx, to_idx)

    res = q.execute()
    data = res.data or []
    total = int(getattr(res, "count", 0) or 0)

    rows: List[Dict] = []
    for r in data:
        rows.append({
            "person_id": r["person_id"],
            "fullname": build_fullname(r),
            "address": "—",  # keep simple for now; we can enrich later
        })
    return rows, total


def get_resident_full_profile(person_id: int) -> Optional[Dict]:
    res = supabase.rpc("get_specific_resident_full_profile", {"p_person_id": person_id}).execute()
    rows = res.data or []
    return rows[0] if rows else None

def build_address_line(r: Dict) -> str:
    a = r.get("addresss") or {}
    s = (a.get("street") or {})
    street = (s.get("street_name") or "").strip()
    purok = ((s.get("purok_sitio") or {}).get("purok_sitio_name") or "").strip()
    brgy  = ((s.get("barangay") or {}).get("barangay_name") or "").strip()
    city  = ((s.get("city") or {}).get("city_name") or "").strip()
    parts = [p for p in [street, purok, brgy, city] if p]
    return ", ".join(parts) if parts else "—"