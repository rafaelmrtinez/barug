from __future__ import annotations
from typing import Any, Dict, List
from authentication.supabase_client import supabase

def list_requests(q: str | None, statuses: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    query = supabase.table("v_doc_request_list_ex").select("*").order("doc_request_id", desc=True)
    if statuses:
        query = query.in_("status", statuses)
    if q:
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.cs.{{{q}}},purposes.cs.{{{q}}}")
    res = query.limit(limit).execute()
    return res.data or []

def list_business_requests(q: str | None, statuses: List[str], limit: int = 50) -> List[Dict[str, Any]]:
    query = supabase.table("v_doc_request_list_ex_v2").select("*").order("doc_request_id", desc=True)
    if statuses:
        query = query.in_("status", statuses)
    if q:
        query = query.or_(f"request_code.ilike.%{q}%,doc_types.cs.{{{q}}},purposes.cs.{{{q}}}")
    res = query.limit(limit).execute()
    return res.data or []

def fetch_detail_bundle(doc_request_id: int) -> Dict[str, Any]:
    res = supabase.rpc("fetch_doc_request_detail_bundle", {"p_doc_request_id": doc_request_id}).execute()
    if getattr(res, "error", None):
        raise RuntimeError(getattr(res.error, "message", "RPC error"))
    return res.data or {}

def build_auth_links(settings, header: Dict[str, Any], lines: List[Dict[str, Any]]):
    BUCKET = "authorization-letters"
    supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
    public_prefix = f"{supabase_url}/storage/v1/object/public/{BUCKET}/" if supabase_url else ""
    seen, paths = set(), []
    for p in (header.get("auth_letter_paths") or []):
        if p and p not in seen: seen.add(p); paths.append(p)
    for ln in lines:
        p = (ln.get("details") or {}).get("auth_letter_path")
        if p and p not in seen: seen.add(p); paths.append(p)
    auth_links = []
    for p in paths:
        name = str(p).split("/")[-1]
        url = (public_prefix + str(p).lstrip("/")) if public_prefix else ""
        auth_links.append({"name": name, "url": url, "is_pdf": name.lower().endswith(".pdf")})
    return auth_links
