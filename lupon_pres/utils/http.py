# lupon_pres/utils/http.py
"""
HTTP utilities for lupon_pres - mirrors lupon_mem.utils.http
"""
from __future__ import annotations
from typing import Any, Dict
from django.http import JsonResponse, HttpRequest
from django.contrib import messages
from django.shortcuts import redirect
from functools import wraps

def json_ok(data: Any = None, **kwargs) -> JsonResponse:
    """Return successful JSON response"""
    response_data = {"status": "success"}
    if data is not None:
        response_data["data"] = data
    response_data.update(kwargs)
    return JsonResponse(response_data)

def json_err(message: str, **kwargs) -> JsonResponse:
    """Return error JSON response"""
    response_data = {"status": "error", "message": message}
    response_data.update(kwargs)
    return JsonResponse(response_data, status=400)

def flash_success(request: HttpRequest, message: str):
    """Add success message"""
    messages.success(request, message)

def flash_warning(request: HttpRequest, message: str):
    """Add warning message"""
    messages.warning(request, message)

def require_post_view(view_func):
    """Decorator to require POST method"""
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if request.method != 'POST':
            messages.error(request, "This action requires POST method.")
            return redirect(request.META.get('HTTP_REFERER', '/'))
        return view_func(request, *args, **kwargs)
    return wrapper