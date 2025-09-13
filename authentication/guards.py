from functools import wraps
from django.shortcuts import redirect

def session_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("auth"):
            return redirect("authentication:login")
        return view_func(request, *args, **kwargs)
    return _wrapped

def role_required(*allowed_roles):
    allowed = {r.lower() for r in allowed_roles}
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            auth = request.session.get("auth") or {}
            role = (auth.get("role_name") or "").lower()
            if role not in allowed:
                return redirect("authentication:login")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
