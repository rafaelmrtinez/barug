from __future__ import annotations

from typing import Any, Dict, List
import logging

from authentication.supabase_client import supabase

logger = logging.getLogger(__name__)

_DOC_TYPES_ALL_CACHE: List[str] = []

def fetch_doc_types_all() -> List[str]:
    """Get the full list of document type names for the filter panel (with simple process cache)."""
    global _DOC_TYPES_ALL_CACHE
    if _DOC_TYPES_ALL_CACHE:
        return _DOC_TYPES_ALL_CACHE
    try:
        res = (
            supabase.table("request_document_type")
            .select("request_document_type_name")
            .order("request_document_type_name")
            .execute()
        )
        names = [
            (r.get("request_document_type_name") or "").strip()
            for r in (res.data or [])
            if (r.get("request_document_type_name") or "").strip()
        ]
        _DOC_TYPES_ALL_CACHE = names
        return names
    except Exception as e:
        logger.warning("Failed to fetch doc types list: %s", e)
        return []
