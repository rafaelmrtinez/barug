# common/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.conf import settings

def staff_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.session.get("user") or {}
        if (user.get("user_type") or user.get("role") or "").upper() != "STAFF":
            return redirect(f"{settings.LOGIN_URL}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)
    return _wrapped
