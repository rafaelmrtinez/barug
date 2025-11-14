# lupon_mem/utils/http.py
from __future__ import annotations
import json
from typing import Any, Callable, Dict, Optional
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib import messages

def json_ok(data: dict | None = None, **extra) -> JsonResponse:
    d = {"ok": True}
    if data: d["data"] = data
    d.update(extra)
    return JsonResponse(d)

def json_err(msg: str, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": msg}
    payload.update(extra)
    return JsonResponse(payload, status=status)

def parse_json(request: HttpRequest) -> Dict[str, Any]:
    try:
        return json.loads(request.body or "{}")
    except Exception:
        return {}

def flash_success(request: HttpRequest, msg: str) -> None:
    messages.success(request, msg)

def flash_warning(request: HttpRequest, msg: str) -> None:
    messages.warning(request, msg)

def require_post_view(view: Callable[[HttpRequest], Any]):
    """Same as @require_POST but keeps our import surface in one place."""
    return require_POST(view)
