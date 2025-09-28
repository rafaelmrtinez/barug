# guards.py
from functools import wraps
from django.shortcuts import render, redirect
from django.urls import reverse

def session_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("auth"):
            return redirect("authentication:login")
        return view_func(request, *args, **kwargs)
    return _wrapped

def _safe_home_url(role_lower: str) -> str:
    """
    Best-effort home url based on role_lower.
    Keep this tiny to avoid circular imports.
    """
    role = (role_lower or "").strip().lower()
    try:
        if role in {"barangay clerk", "clerk"}:
            return reverse("clerk:dashboard")
        if role in {"barangay captain", "captain"}:
            return reverse("captain:dashboard")
        if role in {"barangay health worker", "bhw"}:
            return reverse("bhw:dashboard")
        if role in {"midwife", "barangay midwife"}:
            return reverse("midwife:dashboard")
        if role in {"barangay treasurer", "treasurer"}:
            return reverse("treasurer:queue")
        if role in {"barangay secretary", "secretary"}:
            return reverse("secretary:staff_selection")
        if role in {"nurse", "barangay nurse"}:
            return reverse("nurse:dashboard")
    except Exception:
        pass
    # fallback
    return reverse("authentication:login")

def role_required(*allowed_roles):
    """
    Case-insensitive role guard.
    - If not logged in: redirect to login.
    - If logged in but role NOT allowed: render 403 Unauthorized page.
    """
    allowed = {str(r).strip().lower() for r in allowed_roles}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            auth = request.session.get("auth")
            if not auth:
                return redirect("authentication:login")

            role_lower = (auth.get("role_lower") or auth.get("role_name") or "").strip().lower()
            if allowed and role_lower not in allowed:
                context = {
                    "requested_path": request.path,
                    "role_name": role_lower,
                    "home_url": _safe_home_url(role_lower),
                }
                return render(request, "unauthorized.html", context, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
