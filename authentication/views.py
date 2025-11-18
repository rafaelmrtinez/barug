import logging 
from functools import wraps

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.core.cache import cache
from django.db import DatabaseError
from django.urls import reverse

from .forms import LoginForm, ForgotPasswordForm, NewPasswordForm, ChangePasswordForm, VerificationCodeForm
from .db import call_staff_login, call_change_staff_password, call_staff_request_password_reset, call_staff_reset_password_with_token, call_staff_check_password_reset_token
from common.flash import flash_warning, flash_success, flash_system_error, flash_db_error
from common.send_email import send_email 
from urllib.parse import urlencode


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
    is_super_admin = role in {"super admin", "superadmin", "super-admin"}
    is_admin    = role in {"admin", "barangay admin"}  # << NEW

    # NEW: Lupon roles
    is_lupon_member = role in {
        "barangay lupon member",
        "lupon member",
        "lupon",
        "lupong tagapamayapa member",
    }
    is_lupon_president = role in {
        "barangay lupon president",
        "lupon president",
        "lupon chairman",      # common synonym
        "pangkat chairman",    # when acting as chair of pangkat
    }

    if is_clerk:            return "clerk:dashboard"
    if is_captain:          return "captain:dashboard"
    if is_bhw:              return "bhw:dashboard"
    if is_midwife:          return "midwife:dashboard"
    if is_treas:            return "treasurer:queue"
    if is_secy:             return "secretary:dashboard"
    if is_nurse:            return "nurse:dashboard"
    if is_admin:            return "staff_admin:dashboard"     # << NEW
    if is_super_admin:      return "metrics:health_check"

    # NEW: targets for Lupon roles (separate apps)
    if is_lupon_member:     return "lupon_mem:dashboard"
    if is_lupon_president:  return "lupon_pres:dashboard"

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
    # Clear any existing force_password_change session
    if "force_password_change" in request.session:
        request.session.pop("force_password_change", None)
    
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
            row = call_staff_login(username, (form.cleaned_data.get("password") or ""), ip)
            logger.debug("RPC returned | user=%s row=%s", username, bool(row))
        except DatabaseError as e:
            msg = str(e)
            logger.error("[DEBUG] RPC ERROR | user=%s msg=%s", username, msg, exc_info=False)
            cache.set(rl_key, fail_count + 1, RATE_LIMIT_WINDOW)

            if "Account does not exist" in msg:
                messages.error(request, "Invalid username or password.", extra_tags="auth")
            elif "Wrong password" in msg or "Incorrect password" in msg:
                messages.error(request, "Invalid username or password.", extra_tags="auth")
            elif "Account is not active" in msg:
                messages.error(request, "This account is not active. For assistance, please reach out to your system administrator.", extra_tags="auth")
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
        staff_id, person_id, user_type, role_name_db, first_name, middle_name, last_name, account_status_name = row
        role_lower = (role_name_db or "").strip().lower()
        acc_status_upper = (account_status_name or "").strip().upper()

        # Check if account is PENDING - redirect to forgot password
        # SPECIAL CASE: PENDING → force password reset BEFORE full login
        if acc_status_upper == "PENDING":
            logger.debug(
                "LOGIN PENDING | user=%s staff_id=%s acc_status=%s",
                username, staff_id, account_status_name
            )

            # Minimal session info for password-change flow ONLY
            request.session.cycle_key()
            request.session["force_password_change"] = {
                "staff_id": staff_id,
                "person_id": person_id,
                "user_type": user_type,
                "username": username,
                "ip": ip,
                "created_at": timezone.now().isoformat(),
            }

            # Clear rate-limit counter because creds were correct
            cache.delete(rl_key)

            flash_warning(
                request,
                "Your account is pending activation. Please set a new password to activate your account."
            )
            
            # Direct to your "Change Password" screen, not forgot password
            return redirect("authentication:new_password")

        logger.debug(
            "LOGIN OK | user=%s staff_id=%s person_id=%s role=%s (normalized=%s) acc_status=%s",
            username, staff_id, person_id, role_name_db, role_lower, account_status_name
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


@csrf_protect  # ADDED FORGOT PASS
def forgot_password(request):  # ADDED FORGOT PASS
    """
    Handle staff forgot-password flow:
    - Accepts an email address.
    - Asks the DB to create one or more password reset tokens for all staff
      accounts associated with that email.
    - Sends a single email listing reset links for each account.
    - Always shows a generic success message to avoid email enumeration.
    """  # ADDED FORGOT PASS

    # ADDED FORGOT PASS (helper): shared logic for initial + resend flows
    def _process_password_reset(email: str, ip: str):  # ADDED FORGOT PASS
        """
        Internal helper:
        - Calls DB to generate reset tokens
        - Sends a single email with one or more reset links
        Does NOT raise to caller; all errors are logged only.
        """  # ADDED FORGOT PASS
        try:
            # One row per staff account associated with this email.
            # Expected tuple: (staff_id, username, email_address, reset_token)
            reset_rows = call_staff_request_password_reset(email, ip)  # ADDED FORGOT PASS
        except DatabaseError as e:
            # Do NOT reveal existence of the email to the user
            logger.error(
                "[DEBUG] FORGOT_PASSWORD ERROR | email=%s msg=%s",
                email, str(e), exc_info=False
            )  # ADDED FORGOT PASS
            reset_rows = []  # ADDED FORGOT PASS

        # Build and send one email containing links for all accounts (if any)
        try:  # ADDED FORGOT PASS
            if not reset_rows:
                return  # Nothing to send; still keep response generic to user  # ADDED FORGOT PASS

            accounts = []  # ADDED FORGOT PASS
            target_email = email  # ADDED FORGOT PASS

            from .models import Authentication  # ADDED FORGOT PASS

            for row in reset_rows:  # ADDED FORGOT PASS
                if len(row) < 4:
                    continue
                staff_id, username, row_email, reset_token = row
                if not reset_token:
                    continue

                # Build URL: /auth/new_password/?token=<encoded-token>
                base_url = reverse("authentication:new_password")  # ADDED FORGOT PASS
                query = urlencode({"token": reset_token})          # ADDED FORGOT PASS
                reset_url = request.build_absolute_uri(f"{base_url}?{query}")  # ADDED FORGOT PASS

                # Optional: get role to show nicer label (e.g., "juan.clerk (Barangay Clerk)")
                try:  # ADDED FORGOT PASS
                    profile = Authentication.get_staff_profile_by_id(staff_id)
                    role = profile.get('role', '').title() if profile else ''
                    display_name = f"{username} ({role})" if role else (username or f"Account {staff_id}")
                except Exception:
                    display_name = username or f"Account {staff_id}"

                accounts.append({
                    "username": display_name,
                    "reset_url": reset_url,
                })  # ADDED FORGOT PASS

            if not accounts:
                return  # ADDED FORGOT PASS

            subject = "Password Reset Request"  # ADDED FORGOT PASS

            # Plain-text version  # ADDED FORGOT PASS
            body_text = (
                "You (or someone using this email address) requested a password reset.\n\n"
            )
            if len(accounts) == 1:
                acc = accounts[0]
                body_text += (
                    f"To reset your password for {acc['username']}, "
                    f"click the link below:\n{acc['reset_url']}\n\n"
                )
            else:
                body_text += (
                    "Multiple staff accounts are associated with this email. "
                    "Choose which account you want to reset:\n\n"
                )
                for acc in accounts:
                    body_text += f"• {acc['username']}: {acc['reset_url']}\n"
                body_text += "\n"

            body_text += (
                "If you did not request this, you can safely ignore this email."
            )

            # HTML version  # ADDED FORGOT PASS
            body_html = """
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">Password Reset Request</h2>
                <p>You (or someone using this email address) requested a password reset.</p>
            """

            if len(accounts) == 1:
                acc = accounts[0]
                body_html += f"""
                <p>To reset your password for <strong>{acc['username']}</strong>, click the button below:</p>
                <p style="text-align:center; margin: 24px 0;">
                    <a href="{acc['reset_url']}"
                       style="background:#dc3545;color:#fff;text-decoration:none;
                              padding:12px 24px;border-radius:4px;display:inline-block;">
                        Reset Password
                    </a>
                </p>
                """
            else:
                body_html += """
                <p>Multiple staff accounts are associated with this email. Choose the account you want to reset:</p>
                <div style="margin: 20px 0;">
                """
                for acc in accounts:
                    body_html += f"""
                    <div style="margin: 10px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
                        <strong>{acc['username']}</strong><br>
                        <a href="{acc['reset_url']}"
                           style="background:#dc3545;color:#fff;text-decoration:none;
                                  padding:8px 16px;border-radius:4px;display:inline-block;margin-top:8px;">
                            Reset Password for this Account
                        </a>
                    </div>
                    """
                body_html += "</div>"

            body_html += """
                <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
                <p style="color:#666;font-size:13px;">
                    If you did not request this change, you can safely ignore this email.
                </p>
            </div>
            """

            # Send single email with all reset links  # ADDED FORGOT PASS
            send_email(
                subject=subject,
                to=[target_email],
                body_text=body_text,
                body_html=body_html,
                from_name="Barangay Sto. Niño",
                fail_silently=True,
            )  # ADDED FORGOT PASS

        except Exception as e:
            logger.error(
                "[DEBUG] FORGOT_PASSWORD send_email ERROR | email=%s msg=%s",
                email, str(e), exc_info=True
            )  # ADDED FORGOT PASS

    # ─────────────────────────────────────────────
    # RESEND: handle "request another email" link
    # ─────────────────────────────────────────────
    if request.method == "GET" and request.GET.get("resend") == "1":
        # Reuse the last email used for forgot-password in this session
        email = (request.session.get("forgot_pass_email") or "").strip()
        if not email:
            flash_warning(
                request,
                "Please enter your email again to request another reset link."
            )
            return redirect("authentication:forgot_password")

        ip = _get_client_ip(request)

        # ADDED RATE LIMIT (resend)
        rl_key = f"forgot:rl:{ip}"
        attempts = cache.get(rl_key, 0)
        if attempts >= 5:
            flash_success(
                request,
                "If an account is associated with that email, you'll receive a password reset link shortly."
            )
            return redirect("authentication:email_sent")
        cache.set(rl_key, attempts + 1, 15 * 60)
        # END RATE LIMIT

        _process_password_reset(email, ip)

        flash_success(
            request,
            "If an account is associated with that email, you'll receive a password reset link shortly."
        )
        return redirect("authentication:email_sent")


    # ─────────────────────────────────────────────
    # Normal POST: user submits email in the form
    # ─────────────────────────────────────────────
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = (form.cleaned_data.get("email") or "").strip()
            ip = _get_client_ip(request)

            # ADDED RATE LIMIT (initial forgot)
            rl_key = f"forgot:rl:{ip}:{email.lower()}"
            attempts = cache.get(rl_key, 0)
            if attempts >= 5:
                flash_success(
                    request,
                    "If an account is associated with that email, you'll receive a password reset link shortly."
                )
                return redirect("authentication:email_sent")
            cache.set(rl_key, attempts + 1, 15 * 60)
            # END RATE LIMIT

            # Remember this email in session for "request another email"
            request.session["forgot_pass_email"] = email

            # Do the DB + email process via helper
            _process_password_reset(email, ip)

            flash_success(
                request,
                "If an account is associated with that email, you'll receive a password reset link shortly."
            )
            return redirect("authentication:email_sent")

        return render(request, "forgot_password.html", {"form": form})
    
    # ─────────────────────────────────────────────
    # Default GET – show empty forgot-password form
    # ─────────────────────────────────────────────
    form = ForgotPasswordForm()
    return render(request, "forgot_password.html", {"form": form})







# @require_http_methods(["GET", "POST"])
def new_password(request):
    from django.utils import timezone
    from datetime import datetime
    
    token = request.GET.get("token") or request.POST.get("token")
    is_forgot_mode = bool(token)

    # ─────────────────────────────────────────────
    # FORGOT PASSWORD MODE (via email token)
    # ─────────────────────────────────────────────
    if is_forgot_mode:
        # GET: validate token BEFORE showing form
        if request.method == "GET":
            try:
                is_valid = call_staff_check_password_reset_token(token)
            except DatabaseError as e:
                logger.error(
                    "[DEBUG] CHECK_RESET_TOKEN ERROR | token=%s msg=%s",
                    token, str(e), exc_info=False
                )
                is_valid = False

            if not is_valid:
                flash_warning(
                    request,
                    "This password reset link is invalid or has expired. Please request a new one."
                )
                return redirect("authentication:forgot_password")

            form = NewPasswordForm()
            return render(
                request,
                "new_password.html",
                {"form": form, "mode": "forgot", "token": token},
            )

        # POST: validate + reset via token (UNCHANGED)
        form = NewPasswordForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "new_password.html",
                {"form": form, "mode": "forgot", "token": token},
            )

        new_password_val = form.cleaned_data.get("new_pass")
        confirm_password = form.cleaned_data.get("confirm_pass")

        if new_password_val != confirm_password:
            flash_warning(request, "Passwords do not match.")
            return render(
                request,
                "new_password.html",
                {"form": form, "mode": "forgot", "token": token},
            )

        try:
            success = call_staff_reset_password_with_token(
                token, new_password_val, confirm_password
            )

            if success:
                flash_success(
                    request,
                    "Your password has been updated. Please log in with your new password."
                )
                return redirect("authentication:login")
            else:
                flash_system_error(request, "Unable to change password. Please try again.")

        except DatabaseError as e:
            msg = str(e)
            logger.error("[DEBUG] RESET_PASSWORD ERROR | token=%s msg=%s", token, msg, exc_info=False)

            lower_msg = msg.lower()
            if "invalid" in lower_msg or "expired" in lower_msg or "token" in lower_msg:
                flash_warning(
                    request,
                    "This password reset link is invalid or has expired. Please request a new one."
                )
                return redirect("authentication:forgot_password")
            elif "complexity" in lower_msg:
                flash_warning(
                    request,
                    "Password must be at least 8 characters with uppercase, lowercase, digit, and special character."
                )
            else:
                flash_system_error(
                    request,
                    "Unable to change password at this time. Please try again."
                )

        return render(
            request,
            "new_password.html",
            {"form": form, "mode": "forgot", "token": token},
        )

    # ─────────────────────────────────────────────
    # PENDING ACCOUNT MODE (first login, from session)
    # (original code, just indented under the else)
    # ─────────────────────────────────────────────

    # Check if user has force_password_change session (from PENDING login)
    force_data = request.session.get("force_password_change")
    if not force_data:
        return redirect("authentication:login")
    
    # Check session expiration (15 minutes)
    try:
        created_at = datetime.fromisoformat(force_data.get("created_at", ""))
        if (timezone.now() - created_at).total_seconds() > 900:  # 15 minutes
            request.session.pop("force_password_change", None)
            # flash_warning(request, "Your password reset session has expired. Please try again.")
            return redirect("authentication:login")
    except (ValueError, TypeError):
        request.session.pop("force_password_change", None)
        # flash_system_error(request, "Invalid session. Please try again.")
        return redirect("authentication:login")
    
    # GET request
    if request.method == "GET":
        form = NewPasswordForm()
        return render(request, "new_password.html", {"form": form, "mode": "pending"})
    
    # POST request
    form = NewPasswordForm(request.POST)
    if not form.is_valid():
        return render(request, "new_password.html", {"form": form, "mode": "pending"})
    
    new_password_val = form.cleaned_data.get("new_pass")
    confirm_password = form.cleaned_data.get("confirm_pass")
    
    if new_password_val != confirm_password:
        flash_warning(request, "Passwords do not match.")
        return render(request, "new_password.html", {"form": form, "mode": "pending"})
    
    try:
        # Call secure database function
        success = call_change_staff_password(force_data["staff_id"], new_password_val, confirm_password)
        
        if success:
            # Send email notification
            try:
                from common.send_email import send_email
                import pytz
                
                # Get staff email from force_data or database
                staff_email = force_data.get("email")  # if available in session
                if not staff_email:
                    # Get from database if not in session
                    from .models import Authentication
                    profile = Authentication.get_staff_profile_by_id(force_data["staff_id"])
                    staff_email = profile.get("email_address")
                
                if staff_email:
                    # Get Philippines timezone
                    ph_tz = pytz.timezone('Asia/Manila')
                    ph_time = timezone.now().astimezone(ph_tz)
                    
                    # Compose full name
                    first_name = force_data.get("first_name", "")
                    last_name = force_data.get("last_name", "")
                    full_name = f"{first_name} {last_name}".strip() or "Staff Member"
                    
                    subject = "Password Changed Successfully"
                    body_text = f"Hello {full_name},\n\nYour password has been successfully changed on {ph_time.strftime('%B %d, %Y at %I:%M %p')}.\n\nIf you did not make this change, please contact your administrator immediately.\n\nBest regards,\nBarangay Sto. Niño"
                    body_html = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #333;">Password Changed Successfully</h2>
                        <p>Hello {full_name},</p>
                        <p>Your password has been successfully changed on <strong>{ph_time.strftime('%B %d, %Y at %I:%M %p')}</strong>.</p>
                        <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #28a745;">
                            <p style="margin: 0; color: #155724;"><strong>Security Notice:</strong> If you did not make this change, please contact your administrator immediately.</p>
                        </div>
                        <p>Best regards,<br>Barangay Sto. Niño</p>
                    </div>
                    """
                    
                    send_email(
                        subject=subject,
                        to=[staff_email],
                        body_text=body_text,
                        body_html=body_html,
                        from_name="Barangay Sto. Niño",
                        fail_silently=True
                    )
            except Exception as e:
                logger.error("Failed to send password change notification: %s", str(e), exc_info=True)
            
            # Clear the force change session
            request.session.pop("force_password_change", None)
            
            flash_success(request, "Your password has been updated. Please log in with your new password.")
            return redirect("authentication:login")
        else:
            flash_system_error(request, "Unable to change password. Please try again.")
            
    except DatabaseError as e:
        msg = str(e)
        logger.error("[DEBUG] CHANGE_PASSWORD ERROR | staff=%s msg=%s", force_data["staff_id"], msg, exc_info=False)
        
        if "do not match" in msg:
            flash_warning(request, "Passwords do not match.")
        elif "complexity" in msg:
            flash_warning(request, "Password must be at least 8 characters with uppercase, lowercase, digit, and special character.")
        else:
            flash_system_error(request, "Unable to change password at this time. Please try again.")
    
    return render(request, "new_password.html", {"form": form, "mode": "pending"})




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



@staff_login_required
def account_settings(request):
    from .models import Authentication
    import os
    from django.conf import settings
    from supabase import create_client
    from django.db import DatabaseError, OperationalError, IntegrityError
    from common.flash import flash_success, flash_system_error, flash_db_error
    
    auth = request.session.get("auth", {})
    staff_id = auth.get('staff_id')
    
    if not staff_id:
        messages.error(request, "Staff ID not found in session.", extra_tags="auth")
        return redirect("authentication:login")
    
    # Handle sending verification code
    if request.method == 'POST' and request.POST.get('form_type') == 'send_code':
        import secrets
        import string
        from common.send_email import send_email
        from django.http import JsonResponse
        
        try:
            # Verify current password first
            current_password = request.POST.get('current_password', '').strip()
            if not current_password:
                return JsonResponse({'success': False, 'error': 'Current password is required'})
            
            # Check if current password is correct
            is_valid = Authentication.check_staff_current_password(staff_id, current_password)
            if not is_valid:
                return JsonResponse({'success': False, 'error': 'Current password is incorrect'})
            
            # Generate 6-digit code
            code = ''.join(secrets.choice(string.digits) for _ in range(6))
            
            # Store code in session with expiry
            from django.utils import timezone as tz
            request.session['verification_code'] = code
            request.session['verification_code_expiry'] = (tz.now() + tz.timedelta(minutes=5)).isoformat()
            
            # Get user email
            profile = Authentication.get_staff_profile_by_id(staff_id)
            email = profile.get('email_address')
            
            if not email:
                return JsonResponse({'success': False, 'error': 'No email address found'})
            
            # Send email
            subject = 'Password Change Verification Code'
            body_text = f'Your verification code is: {code}\n\nThis code will expire in 5 minutes.'
            body_html = f'''
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">Password Change Verification</h2>
                <p>Your verification code is:</p>
                <div style="background: #f8f9fa; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                    <h1 style="color: #dc3545; font-size: 32px; margin: 0; letter-spacing: 8px;">{code}</h1>
                </div>
                <p style="color: #666;">This code will expire in 5 minutes.</p>
                <p style="color: #666;">If you did not request this code, please ignore this email.</p>
            </div>
            '''
            
            resp = send_email(
                subject=subject,
                to=[email],
                body_text=body_text,
                body_html=body_html,
                from_name="Barangay Sto. Niño",
                fail_silently=False
            )
            
            if getattr(resp, 'ok', False):
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to send verification email. Please check your email address or try again later.'})
                
        except Exception as e:
            logger.error(f"Error sending verification code: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Failed to send verification email. Please check your email address or try again later.'})
    
    # Handle resend verification code
    if request.method == 'POST' and request.POST.get('form_type') == 'resend_code':
        import secrets
        import string
        from common.send_email import send_email
        from django.http import JsonResponse
        
        try:
            # Generate new 6-digit code
            code = ''.join(secrets.choice(string.digits) for _ in range(6))
            
            # Store code in session with expiry
            from django.utils import timezone as tz
            request.session['verification_code'] = code
            request.session['verification_code_expiry'] = (tz.now() + tz.timedelta(minutes=5)).isoformat()
            
            # Get user email
            profile = Authentication.get_staff_profile_by_id(staff_id)
            email = profile.get('email_address')
            
            if not email:
                return JsonResponse({'success': False, 'error': 'No email address found'})
            
            # Send email
            subject = 'Password Change Verification Code'
            body_text = f'Your verification code is: {code}\n\nThis code will expire in 5 minutes.'
            body_html = f'''
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">Password Change Verification</h2>
                <p>Your verification code is:</p>
                <div style="background: #f8f9fa; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                    <h1 style="color: #dc3545; font-size: 32px; margin: 0; letter-spacing: 8px;">{code}</h1>
                </div>
                <p style="color: #666;">This code will expire in 5 minutes.</p>
                <p style="color: #666;">If you did not request this code, please ignore this email.</p>
            </div>
            '''
            
            resp = send_email(
                subject=subject,
                to=[email],
                body_text=body_text,
                body_html=body_html,
                from_name="Barangay Sto. Niño",
                fail_silently=False
            )
            
            if getattr(resp, 'ok', False):
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to resend verification email. Please try again later.'})
                
        except Exception as e:
            logger.error(f"Error resending verification code: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Failed to resend verification email. Please try again later.'})
    
    # Handle code verification and password change
    if request.method == 'POST' and request.POST.get('form_type') == 'verify_change_password':
        from django.http import JsonResponse
        from datetime import datetime
        
        try:
            code = request.POST.get('code', '').strip()
            current_password = request.POST.get('current_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            
            # Rate limit verification attempts
            verify_key = f"verify_attempts:{staff_id}"
            attempts = cache.get(verify_key, 0)
            if attempts >= 3:
                return JsonResponse({'success': False, 'error': 'Too many verification attempts. Please request a new code.'})
            
            # Increment attempt counter
            cache.set(verify_key, attempts + 1, 300)  # 5 minutes
            
            print(f"SERVER DEBUG: new='{new_password}', confirm='{confirm_password}', match={new_password == confirm_password}")
            
            # Debug logging
            logger.debug(f"Password change attempt - new_password length: {len(new_password)}, confirm_password length: {len(confirm_password)}, match: {new_password == confirm_password}")
            
            # Verify code
            stored_code = request.session.get('verification_code')
            expiry_str = request.session.get('verification_code_expiry')
            
            if not stored_code or not expiry_str:
                return JsonResponse({'success': False, 'error': 'No verification code found. Please request a new code.'})
            
            # Check expiry
            from django.utils import timezone as tz
            try:
                expiry_time = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                if not expiry_time.tzinfo:
                    expiry_time = tz.make_aware(expiry_time)
            except ValueError:
                expiry_time = tz.now() - tz.timedelta(minutes=1)  # Force expired
            
            if tz.now() > expiry_time:
                # Clear expired code from session
                request.session.pop('verification_code', None)
                request.session.pop('verification_code_expiry', None)
                return JsonResponse({'success': False, 'error': 'Verification code has expired. Please request a new code.'})
            
            # Check code match
            if code != stored_code:
                return JsonResponse({'success': False, 'error': 'Invalid verification code. Please try again.'})
            
            # TOCTOU protection: Re-verify current password right before changing
            if not Authentication.check_staff_current_password(staff_id, current_password):
                return JsonResponse({'success': False, 'error': 'Current password verification failed. Please try again.'})
            
            # Change password
            success = Authentication.change_staff_password(staff_id, new_password, confirm_password)
            
            if success:
                # Clear verification code from session and rate limit counter
                request.session.pop('verification_code', None)
                request.session.pop('verification_code_expiry', None)
                cache.delete(verify_key)  # Clear verification attempts
                
                # Send password change notification email
                try:
                    profile = Authentication.get_staff_profile_by_id(staff_id)
                    email = profile.get('email_address')
                    user_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
                    
                    if email:
                        from common.send_email import send_email
                        from django.utils import timezone
                        import pytz
                        
                        # Get Philippines timezone
                        ph_tz = pytz.timezone('Asia/Manila')
                        ph_time = timezone.now().astimezone(ph_tz)
                        
                        subject = 'Password Changed Successfully'
                        body_text = f'Hello {user_name},\n\nYour password has been successfully changed on {ph_time.strftime("%B %d, %Y at %I:%M %p")}.\n\nIf you did not make this change, please contact your administrator immediately.\n\nBest regards,\nBarangay Sto. Niño'
                        body_html = f'''
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <h2 style="color: #333;">Password Changed Successfully</h2>
                            <p>Hello {user_name},</p>
                            <p>Your password has been successfully changed on <strong>{ph_time.strftime("%B %d, %Y at %I:%M %p")}</strong>.</p>
                            <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #28a745;">
                                <p style="margin: 0; color: #155724;"><strong>Security Notice:</strong> If you did not make this change, please contact your administrator immediately.</p>
                            </div>
                            <p>Best regards,<br>Barangay Sto. Niño</p>
                        </div>
                        '''
                        
                        send_email(
                            subject=subject,
                            to=[email],
                            body_text=body_text,
                            body_html=body_html,
                            from_name="Barangay Sto. Niño",
                            fail_silently=True
                        )
                except Exception as e:
                    logger.error(f"Failed to send password change notification: {str(e)}", exc_info=True)
                
                return JsonResponse({'success': True, 'message': 'Password changed successfully!'})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to change password.'})
                
        except (DatabaseError, OperationalError, IntegrityError) as e:
            from common.flash import _extract_psycopg_diag
            logger.error(f"Database error changing password: {str(e)}", exc_info=True)
            pgcode, primary = _extract_psycopg_diag(e)
            error_msg = primary if primary else 'Database error occurred while changing password. Please try again.'
            return JsonResponse({'success': False, 'error': error_msg})
        except Exception as e:
            logger.error(f"Error changing password: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'An error occurred while changing password. Please try again.'})
    
    # Handle clearing verification code
    if request.method == 'POST' and request.POST.get('form_type') == 'clear_code':
        from django.http import JsonResponse
        
        try:
            # Clear verification code from session
            request.session.pop('verification_code', None)
            request.session.pop('verification_code_expiry', None)
            return JsonResponse({'success': True})
        except Exception:
            return JsonResponse({'success': False})
    
    # Handle profile photo upload
    if request.method == 'POST' and 'staff_img' in request.FILES:
        from django.http import JsonResponse
        
        try:
            profile = Authentication.get_staff_profile_by_id(staff_id)
            if not profile:
                return JsonResponse({'success': False, 'error': 'Profile not found'})
            
            uploaded_file = request.FILES['staff_img']
            
            # Generate folder key from personal data
            import re
            from datetime import datetime as _dt
            from io import BytesIO
            
            def _prep_image_for_upload(file_obj, *, max_w=2200, max_h=2200):
                try:
                    from PIL import Image, ImageOps
                    file_obj.seek(0)
                    img = Image.open(file_obj)
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((max_w, max_h))
                    has_alpha = (img.mode in ("RGBA", "LA")) or ("transparency" in img.info)
                    if has_alpha:
                        if img.mode not in ("RGBA", "LA"):
                            img = img.convert("RGBA")
                        buf = BytesIO()
                        img.save(buf, format="PNG", optimize=True)
                        buf.seek(0)
                        return buf, "image/png", "png"
                    else:
                        if img.mode not in ("RGB", "L"):
                            img = img.convert("RGB")
                        buf = BytesIO()
                        img.save(buf, format="JPEG", quality=85, optimize=True)
                        buf.seek(0)
                        return buf, "image/jpeg", "jpg"
                except Exception:
                    try:
                        file_obj.seek(0)
                    except Exception:
                        pass
                    return file_obj, getattr(file_obj, "content_type", "application/octet-stream"), "jpg"
            
            def _key_from_personal(personal: dict) -> str:
                last  = (personal.get("last_name")   or "").strip()
                first = (personal.get("first_name")  or "").strip()
                mid   = (personal.get("middle_name") or "").strip()
                initials = (last[:1] + first[:1] + mid[:1]).lower()
                b = personal.get("birth_date")
                b_dt = None
                if isinstance(b, str) and b:
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                        try:
                            b_dt = _dt.strptime(b, fmt).date()
                            break
                        except Exception:
                            pass
                b_str = b_dt.strftime("%m%d%Y") if b_dt else ""
                mobile_raw = (personal.get("mobile_number") or "").strip()
                mobile_digits = re.sub(r"\D+", "", mobile_raw)
                last8 = mobile_digits[-8:] if mobile_digits else ""
                return f"{initials}{b_str}{last8}"
            
            # Process image and get proper format
            buf, mime, ext = _prep_image_for_upload(uploaded_file)
            folder_key = _key_from_personal(profile)
            
            # Create Supabase client
            supabase = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            
            # Upload to Supabase Storage with proper extension
            file_path = f"{folder_key}/profile_picture.{ext}"
            
            # Upload file (will replace if exists)
            file_data = buf.read() if hasattr(buf, 'read') else buf
            if hasattr(buf, 'seek'):
                buf.seek(0)  # Reset buffer position
            
            upload_result = supabase.storage.from_("staff-profile-picture").upload(
                file_path,
                file_data,
                file_options={"content-type": mime, "upsert": "true"}
            )
            
            # Get public URL
            public_url = supabase.storage.from_("staff-profile-picture").get_public_url(file_path)
            
            # Extract the actual URL from the response
            if hasattr(public_url, 'get'):
                public_url = public_url.get('publicUrl') or public_url.get('publicURL') or str(public_url)
            elif hasattr(public_url, 'publicUrl'):
                public_url = public_url.publicUrl
            else:
                public_url = str(public_url)
            
            # Update database
            Authentication.set_staff_photo(staff_id, public_url)
            
            return JsonResponse({
                'success': True, 
                'message': 'Profile photo updated successfully!',
                'new_image_url': public_url
            })
            
        except (DatabaseError, OperationalError, IntegrityError) as e:
            logger.error(f"Database error during profile photo upload: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Database error occurred while updating profile photo'})
        except Exception as e:
            logger.error(f"Profile photo upload failed: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Failed to update profile photo'})
    
    # Get profile from database
    try:
        profile = Authentication.get_staff_profile_by_id(staff_id)
        if not profile:
            flash_system_error(request, "Profile not found.")
            return redirect("authentication:login")
    except (DatabaseError, OperationalError, IntegrityError) as e:
        logger.error(f"Database error loading profile: {str(e)}", exc_info=True)
        flash_db_error(request, e)
        return redirect("authentication:login")
    except Exception as e:
        logger.error(f"Error loading profile: {str(e)}", exc_info=True)
        flash_system_error(request, "Failed to load profile data", exc=e)
        return redirect("authentication:login")
    
    # Format name: First Middle_Initial Last Suffix
    first = (profile.get('first_name') or '').strip().title()
    middle = (profile.get('middle_name') or '').strip()
    last = (profile.get('last_name') or '').strip().title()
    suffix = (profile.get('suffix') or '').strip().title()
    
    name_parts = [first]
    if middle:
        name_parts.append(f"{middle[0].upper()}.")
    if last:
        name_parts.append(last)
    if suffix:
        name_parts.append(suffix)
    
    user_fullname = ' '.join(name_parts)
    role_title = (profile.get('role') or '').title()
    
    # Security status based on actual data
    account_status = (profile.get('account_status') or '').lower()
    is_account_active = account_status == 'active'
    is_secure_pass = profile.get('is_secure_pass', False)
    
    return render(request, "account_settings.html", {
        'user_fullname': user_fullname,
        'user_role': role_title,
        'staff_id': staff_id,
        'staff_code': profile.get('staff_code'),
        'page_path': f"{role_title} / Account Settings",
        'page_title': 'Account Settings',
        'user_role_template': role_title.lower().replace(' ', '_'),
        'profile': profile,
        'is_account_active': is_account_active,
        'is_secure_pass': is_secure_pass,
        'change_password_form': ChangePasswordForm(),
        'verification_code_form': VerificationCodeForm(),
    })  