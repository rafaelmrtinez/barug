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

    # NEW: targets for Lupon roles (adjust if your URL namespaces differ)
    if is_lupon_member:     return "lupon_mem:dashboard"
    if is_lupon_president:  return "lupon_president:dashboard"

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
            row = call_staff_login(username, (form.cleaned_data.get("password") or ""))
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