# lupon_mem/utils/params.py
from __future__ import annotations
from typing import Any, Optional

def post_int(request, name: str, default: Optional[int] = None) -> Optional[int]:
    v = (request.POST.get(name) or "").strip()
    return int(v) if v.isdigit() else default

def post_bool(request, name: str) -> bool:
    # works with <input type="checkbox" name="...">
    return bool(request.POST.get(name))

def post_str(request, name: str, default: str = "") -> str:
    return (request.POST.get(name) or default).strip()

def req_int(v: Any, label: str) -> int:
    if v is None: raise ValueError(f"Missing {label}")
    return int(v)
