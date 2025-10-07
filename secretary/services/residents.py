# secretary/services/residents.py
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
    return f"{ln}, {fn}{mid}{suf}".strip().upper()


def build_address_line(r: Dict) -> str:
    """Build 'Street, Purok, Barangay, City' from nested join payload."""
    street = (((r.get("addresss") or {}).get("street") or {}).get("street_name") or "").strip()
    purok = ((((r.get("addresss") or {}).get("street") or {}).get("purok_sitio") or {}).get("purok_sitio_name") or "").strip()
    brgy = ((((r.get("addresss") or {}).get("street") or {}).get("barangay") or {}).get("barangay_name") or "").strip()
    city = ((((r.get("addresss") or {}).get("street") or {}).get("city") or {}).get("city_name") or "").strip()

    parts = [p for p in [street, purok, brgy, city] if p]
    return ", ".join(parts)


def list_residents_minimal(search: str = "", page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
    """
    Returns (rows, total). Each row: {person_id, fullname, address}
    Uses PostgREST nested selects. Keep columns minimal for speed.
    """
    from_idx = (page - 1) * page_size

    # Base select with nested address graph
    select = (
        "person_id,last_name,first_name,middle_name,suffix,"
        "addresss:address_id("
        "  street:street_id("
        "    street_name,"
        "    purok_sitio:purok_sitio_id(purok_sitio_name),"
        "    barangay:barangay_id(barangay_name),"
        "    city:city_id(city_name)"
        "  )"
        ")"
    )

    query = supabase.table("person").select(select)

    if search:
        # Case-insensitive filter on name parts
        ilike = f"%{search}%"
        query = query.or_(
            f"last_name.ilike.{ilike},first_name.ilike.{ilike},middle_name.ilike.{ilike},suffix.ilike.{ilike}"
        )

    # Order and page
    query = query.order("last_name", desc=False).range(from_idx, from_idx + page_size - 1)

    # Fetch rows
    res = query.execute()
    data = res.data or []

    # Total count (PostgREST cannot give exact count via python client easily w/ range,
    # do a lightweight count call)
    cnt_q = supabase.rpc("count_table_rows", {"p_table_name": "person"}).execute() \
        if hasattr(supabase, "rpc") else None
    total = (cnt_q.data or {}).get("count") if cnt_q and cnt_q.data else len(data)

    # Transform
    out: List[Dict] = []
    for r in data:
        out.append({
            "person_id": r["person_id"],
            "fullname": build_fullname(r),
            "address": build_address_line(r),
        })

    return out, int(total)


def get_resident_full_profile(person_id: int) -> Optional[Dict]:
    """
    Wraps your RPC: get_specific_resident_full_profile(p_person_id integer)
    """
    res = supabase.rpc("get_specific_resident_full_profile", {"p_person_id": person_id}).execute()
    rows = res.data or []
    return rows[0] if rows else None
