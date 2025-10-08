import logging
from functools import wraps

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.core.cache import cache
from django.db import DatabaseError
from django.urls import reverse

from .forms import LoginForm, ForgotPasswordForm, NewPasswordForm
from .db import call_staff_login

logger = logging.getLogger(__name__)  # << use module logger

RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 15 * 60


def _get_client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def _role_home(role_name: str) -> str:
    """
    Map normalized (lowercased) role names to URL names.
    Accepts any case but immediately normalizes to lower().
    """
    role = (role_name or "").strip().lower()

    # normalize common variants
    is_clerk    = role in {"barangay clerk", "clerk"}
    is_captain  = role in {"barangay captain", "captain"}
    is_bhw      = role in {"barangay health worker", "bhw"}
    is_midwife  = role in {"midwife", "barangay midwife"}
    is_treas    = role in {"barangay treasurer", "treasurer"}
    is_secy     = role in {"barangay secretary", "secretary"}
    is_nurse    = role in {"nurse", "barangay nurse"}
    is_super_admin = role in {"super admin", "Super Admin"}

    if is_clerk:   return "clerk:dashboard"
    if is_captain: return "captain:dashboard"
    if is_bhw:     return "bhw:dashboard"
    if is_midwife: return "midwife:dashboard"
    if is_treas:   return "treasurer:queue"
    if is_secy:    return "secretary:staff_selection"
    if is_nurse:   return "nurse:dashboard"
    if is_super_admin: return "metrics:health_check"

    logger.debug("Role not matched in _role_home; role=%s -> resident fallback", role)
    return "resident:dashboard"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers / Decorators for auth & role checks
# ──────────────────────────────────────────────────────────────────────────────
def staff_login_required(view_func):
    """Ensure session contains 'auth'. If missing, redirect to login."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("auth"):
            messages.error(request, "Please sign in to continue.", extra_tags="auth")
            return redirect("authentication:login")
        return view_func(request, *args, **kwargs)
    return _wrapped


def roles_required(*role_names):
    """
    Ensure the logged-in staff has one of the allowed roles.
    Role comparison is case-insensitive; both sides are normalized to lower().
    If unauthorized, render the custom Unauthorized page (403).
    """
    allowed = {str(r).strip().lower() for r in role_names}

    def _decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            auth = request.session.get("auth")
            if not auth:
                messages.error(request, "Please sign in to continue.", extra_tags="auth")
                return redirect("authentication:login")

            # Prefer normalized value; fall back to role_name if older sessions exist
            role_now = (auth.get("role_lower") or auth.get("role_name") or "").strip().lower()

            if allowed and role_now not in allowed:
                logger.warning(
                    "UNAUTHORIZED | user=%s role=%s required_any=%s path=%s",
                    auth.get("username"), role_now, allowed, request.path
                )
                try:
                    home_url = reverse(_role_home(role_now))
                except Exception:
                    home_url = reverse("authentication:login")

                return render(
                    request,
                    "unauthorized.html",
                    {
                        "requested_path": request.path,
                        "role_name": role_now,  # already lowercased
                        "home_url": home_url,
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return _wrapped
    return _decorator


@csrf_protect
def login(request):
    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        username = (form.cleaned_data.get("email_username") or "").strip()
        ip = _get_client_ip(request)
        rl_key = f"login:rl:{ip}:{username.lower()}"

        # 1) Rate limit check
        fail_count = cache.get(rl_key, 0)
        logger.debug("[DEBUG] LOGIN start | ip=%s user=%s fail_count=%s", ip, username, fail_count)
        if fail_count >= RATE_LIMIT_ATTEMPTS:
            logger.debug("[DEBUG] RATE_LIMIT_HIT | ip=%s user=%s key=%s", ip, username, rl_key)
            messages.error(
                request,
                "Too many attempts. Please try again in a few minutes.",
                extra_tags="auth",
            )
            return render(request, "authentication_index.html", {"form": form})

        # 2) RPC
        try:
            logger.debug("RPC call_staff_login() | user=%s", username)
            row = call_staff_login(username, form.cleaned_data.get("password") or "")
            logger.debug("RPC returned | user=%s row=%s", username, bool(row))
        except DatabaseError as e:
            msg = str(e)
            logger.error("[DEBUG] RPC ERROR | user=%s msg=%s", username, msg, exc_info=False)
            cache.set(rl_key, fail_count + 1, RATE_LIMIT_WINDOW)

            if "Account does not exist" in msg:
                messages.error(request, "Invalid username or password.", extra_tags="auth")
            elif "Wrong password" in msg or "Incorrect password" in msg:
                messages.error(request, "Invalid username or password.", extra_tags="auth")
            elif "could not translate host name" in msg or "could not connect" in msg:
                messages.error(
                    request,
                    "Login service is temporarily unavailable. Please try again.",
                    extra_tags="auth",
                )
            else:
                messages.error(
                    request,
                    "Login failed due to a server error. Please try again.",
                    extra_tags="auth",
                )
            return render(request, "authentication_index.html", {"form": form})

        # 3) No row case
        if not row:
            logger.debug("RPC returned no row | user=%s (treat as bad creds)", username)
            cache.set(rl_key, fail_count + 1, RATE_LIMIT_WINDOW)
            messages.error(request, "Invalid username or password.", extra_tags="auth")
            return render(request, "authentication_index.html", {"form": form})

        # 4) Success — unpack row
        staff_id, person_id, user_type, role_name_db, first_name, last_name, middle_name = row
        role_lower = (role_name_db or "").strip().lower()

        logger.debug(
            "LOGIN OK | user=%s staff_id=%s person_id=%s role=%s (normalized=%s)",
            username, staff_id, person_id, role_name_db, role_lower
        )

        # 5) Session (store normalized role; keep original in case you ever need it)
        request.session.cycle_key()
        request.session["auth"] = {
            "staff_id": staff_id,
            "person_id": person_id,
            "user_type": user_type,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            # normalized & original
            "role_name": role_lower,          # <<< lowercased for consistent checks
            "role_lower": role_lower,         # <<< redundant but explicit
            "role_original": role_name_db,    # <<< optional, for display/logs if needed
            "username": username,
            "display_name": "",
            "login_at": timezone.now().isoformat(),
        }
        request.session.set_expiry(60 * 60 * 8)

        # Clear rate-limit counter
        cache.delete(rl_key)

        # 6) Redirect using the normalized role
        dest = _role_home(role_lower)
        logger.debug("REDIRECT | user=%s -> %s", username, dest)
        return redirect(dest)

    # GET or invalid form
    if request.method == "POST":
        logger.debug("FORM INVALID | errors=%s", dict(form.errors))
    return render(request, "authentication_index.html", {"form": form})


def logout(request):
    # Clear session
    auth = request.session.get("auth")
    username = auth.get("username") if auth else None
    ip = request.META.get("REMOTE_ADDR", "")
    if username:
        rl_key = f"login:rl:{ip}:{username.lower()}"
        cache.delete(rl_key)  # clear rate-limit counter for this user/ip

    request.session.flush()
    messages.success(request, "You have been logged out.", extra_tags="auth")
    return redirect("authentication:login")


def forgot_password(request):
    form = ForgotPasswordForm()
    return render(request, "forgot_password.html", {"form": form})


def new_password(request):
    form = NewPasswordForm()
    return render(request, "new_password.html", {"form": form})


def email_sent(request):
    return render(request, "email_sent.html")


def email_confirmed(request):
    return render(request, "email_confirmed.html")


def unauthorized(request):
    """
    Direct endpoint to show the Unauthorized page.
    """
    auth = request.session.get("auth")
    role_now = (auth.get("role_lower") or auth.get("role_name") or "").strip().lower() if auth else ""
    if role_now:
        try:
            home_url = reverse(_role_home(role_now))
        except Exception:
            home_url = reverse("authentication:login")
    else:
        home_url = reverse("authentication:login")

    return render(
        request,
        "unauthorized.html",
        {
            "requested_path": request.path,
            "role_name": role_now,  # shown as lowercase on the page
            "home_url": home_url,
        },
        status=403,
    )
