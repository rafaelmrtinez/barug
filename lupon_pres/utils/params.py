# lupon_pres/utils/params.py
"""
Parameter utilities for lupon_pres - mirrors lupon_mem.utils.params
"""
from __future__ import annotations
from typing import Optional
from django.http import HttpRequest

def post_int(request: HttpRequest, key: str, default: Optional[int] = None) -> Optional[int]:
    """Get integer from POST data"""
    value = request.POST.get(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def post_bool(request: HttpRequest, key: str, default: bool = False) -> bool:
    """Get boolean from POST data"""
    value = request.POST.get(key, "").strip().lower()
    if value in ("true", "1", "on", "yes"):
        return True
    elif value in ("false", "0", "off", "no"):
        return False
    return default

def post_str(request: HttpRequest, key: str, default: str = "") -> str:
    """Get string from POST data"""
    value = request.POST.get(key, "").strip()
    return value if value else default