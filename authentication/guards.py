# guards.py - Authentication guards with multi-role support
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
    For users with multiple roles, this determines the primary dashboard.
    """
    role = (role_lower or "").strip().lower()
    try:
        # Priority order for multiple roles (highest priority first)
        if role in {"super admin", "superadmin", "super-admin"}:
            return reverse("superadmin:dashboard")
        if role in {"barangay captain", "captain"}:
            return reverse("captain:dashboard")
        if role in {"admin", "barangay admin"}:
            return reverse("staff_admin:dashboard")
        if role in {"barangay clerk", "clerk"}:
            return reverse("clerk:dashboard")
        if role in {"barangay treasurer", "treasurer"}:
            return reverse("treasurer:queue")
        if role in {"barangay secretary", "secretary"}:
            return reverse("secretary:staff_selection")
        if role in {"midwife", "barangay midwife"}:
            return reverse("midwife:dashboard")
        if role in {"barangay health worker", "bhw"}:
            return reverse("bhw:dashboard")
        if role in {"nurse", "barangay nurse"}:
            return reverse("nurse:dashboard")
        if role in {"barangay lupon president", "lupon president", "lupon chairman", "pangkat chairman"}:
            return reverse("lupon_pres:dashboard")
        if role in {"barangay lupon member", "lupon member", "lupon", "lupong tagapamayapa member"}:
            return reverse("lupon_mem:dashboard")
    except Exception:
        pass
    # fallback
    return reverse("authentication:login")

def role_required(*allowed_roles):
    """
    Case-insensitive role guard with multi-role support.
    - If not logged in: redirect to login.
    - If logged in but user doesn't have any allowed role: render 403 Unauthorized page.
    """
    allowed = {str(r).strip().lower() for r in allowed_roles}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            auth = request.session.get("auth")
            if not auth:
                return redirect("authentication:login")

            # Get user's roles - check both single role and multiple roles
            user_roles = set()
            
            # Add primary role (for backward compatibility)
            primary_role = (auth.get("role_lower") or auth.get("role_name") or "").strip().lower()
            if primary_role:
                user_roles.add(primary_role)
            
            # Add all roles from the list (new multi-role support)
            role_names_list = auth.get("role_names_list", [])
            for role in role_names_list:
                user_roles.add(role.strip().lower())
            
            # Check if user has any of the required roles
            has_required_role = bool(allowed.intersection(user_roles))
            
            if allowed and not has_required_role:
                context = {
                    "requested_path": request.path,
                    "role_name": primary_role,
                    "home_url": _safe_home_url(primary_role),
                }
                return render(request, "unauthorized.html", context, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
