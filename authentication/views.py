import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.core.cache import cache
from django.db import DatabaseError

from .forms import LoginForm, ForgotPasswordForm, NewPasswordForm
from .db import call_staff_login

logger = logging.getLogger(__name__)  # << use module logger

RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 15 * 60

def _get_client_ip(request):
    return request.META.get("REMOTE_ADDR", "")

def _role_home(role_name: str) -> str:
    role = (role_name or "").lower()
    if role == "barangay clerk": return "clerk:dashboard"
    if role == "captain": return "captain:dashboard"
    if role == "bhw": return "clerk:dashboard"
    if role == "barangay treasurer": return "treasurer:queue"
    # Temporary placement just to allow super admin login and avoid crashing the application.
    # Please dont hesitate to change this to the appropriate page.
    if role == "super admin": return "metrics:health_check"
    logger.debug("Role not matched, falling back to resident: %s", role)
    return "resident:dashboard"

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
        staff_id, person_id, user_type, role_name, first_name, last_name, middle_name = row
        logger.debug(
            "LOGIN OK | user=%s staff_id=%s person_id=%s role=%s",
            username, staff_id, person_id, role_name
        )

        # 5) Session
        request.session.cycle_key()
        request.session["auth"] = {
            "staff_id": staff_id,
            "person_id": person_id,
            "user_type": user_type,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "role_name": role_name,
            "username": username,
            "display_name": "",
            "login_at": timezone.now().isoformat(),
        }
        request.session.set_expiry(60 * 60 * 8)

        # Clear rate-limit counter
        cache.delete(rl_key)

        # 6) Redirect
        dest = _role_home(role_name)
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
