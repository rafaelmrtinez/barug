# authentication/decorators.py
from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

def staff_login_required(view_func):
    """
    Protect views using session-only auth.
    Requires request.session["user"] to exist and role == STAFF.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.session.get("user")
        if not user:
            # not logged in
            return redirect("login")
        role = (user.get("role") or "").strip().upper()
        if role != "STAFF":
            # logged in but not staff
            return HttpResponseForbidden("Forbidden: staff only.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def staff_positions_required(*allowed_positions):
    """
    Restrict view access to staff with specific positions.

    Usage:
        @staff_positions_required("CLERK", "BHW")
        def my_view(request): ...
    """
    allowed_norm = {p.strip().upper() for p in allowed_positions}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.session.get("user")
            if not user:
                return redirect("login")

            role = (user.get("role") or "").strip().upper()
            position = (user.get("position") or "").strip().upper()

            if role != "STAFF":
                return HttpResponseForbidden("Forbidden: staff only.")

            if allowed_norm and position not in allowed_norm:
                return HttpResponseForbidden(
                    f"Forbidden: {position or 'Unknown'} not allowed here."
                )

            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator