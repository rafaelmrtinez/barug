# authentication/views.py
from csv import reader
import re
import requests
from typing import Optional

from django.conf import settings
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm
from .cookie_utils import set_auth_cookies  # your existing helper


API_BASE = f"{settings.TESTING_URL_USED}/api/auth"


# --------------------------- helpers ---------------------------

def _extract_error_message(r: requests.Response) -> str:
    """Best-effort extraction of a meaningful error from API."""
    try:
        data = r.json()
        msg = (data.get("message") or data.get("error") or data.get("detail") or "").strip()
        if msg:
            return msg
    except ValueError:
        pass

    text = (r.text or "").strip()
    m = re.search(r"""['"]message['"]\s*:\s*['"]([^'"]+)['"]""", text)
    return m.group(1).strip() if m else "Login failed."

def _norm(s: Optional[str]) -> str:
    """Uppercase + trim + collapse whitespace."""
    return " ".join(str(s or "").upper().strip().split())

def _is_staff_account(user_payload: dict) -> bool:
    """
    Your API returns something like:
      {
        "user_id": 4,
        "username": "brgyclerk",
        "role": "STAFF",
        "position": "BARANGAY CLERK"
      }
    Only allow STAFF in the web portal.
    """
    return _norm(user_payload.get("role")) == "STAFF"

def _primary_staff_position(user_payload: dict) -> str:
    """Pick the specific staff position from payload."""
    return _norm(
        user_payload.get("position")
        or user_payload.get("staff_position")
        or user_payload.get("title")
        or ""
    )

# Map by **POSITION** (normalized)
POSITION_TO_DASHBOARD = {
    "CLERK": "/clerk/review_request/",
    "BARANGAY CLERK": "/clerk/review_request/",
    "BHW": "/bhw/",
    "BARANGAY HEALTH WORKER": "/bhw/",
    "LUPON": "/lupon/",
    "LUPON MEMBER": "/lupon/",
    "LUPON_PRESIDENT": "/lupon/president/",
    "LUPON PRESIDENT": "/lupon/president/",
    "SECRETARY": "/secretary/",
    "BARANGAY SECRETARY": "/secretary/",
    "CAPTAIN": "/captain/",
    "BARANGAY CAPTAIN": "/captain/",
    "PUNONG BARANGAY": "/captain/",
    "ADMIN": "/admin/",
    "SYSTEM ADMIN": "/admin/",
    "MIDWIFE": "/midwife/",
}

def _dashboard_for_position(position_norm: str) -> str:
    return POSITION_TO_DASHBOARD.get(position_norm, "/staff/")  # fallback

def _safe_next(request, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if value.startswith("/") and url_has_allowed_host_and_scheme(value, {request.get_host()}):
        return value
    return None


# --------------------------- views ---------------------------

def login(request):
    """
    Session-only login (no Django User model).
    Stores API payload at request.session["user"] and sets JWT cookies if present.
    """
    if request.method == "POST":
        form = LoginForm(request.POST)
        if not form.is_valid():
            return render(request, "authentication_index.html", {"form": form})

        username = form.cleaned_data["email_username"].strip()
        password = form.cleaned_data["password"]

        # Call your API
        try:
            r = requests.post(
                API_BASE + "/staff-login/",
                json={"username": username, "password": password},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Platform": "web",
                },
                timeout=10,
            )
        except requests.RequestException as e:
            form.add_error(None, f"Login service error: {e}")
            return render(request, "authentication_index.html", {"form": form})

        # Show API message on error
        if r.status_code >= 400:
            form.add_error(None, "Login Failed: " + _extract_error_message(r))
            return render(request, "authentication_index.html", {"form": form})

        # Parse success
        try:
            data = r.json()
        except ValueError:
            form.add_error(None, "Unexpected response from login service.")
            return render(request, "authentication_index.html", {"form": form})

        user_payload = data.get("user") or {}

        # Accept either "access" or "token" naming
        access = data.get("access") or data.get("token")
        refresh = data.get("refresh")

        # Staff-only gate
        if not _is_staff_account(user_payload):
            form.add_error(None, "Only staff can log in on this site. Residents should use the mobile app.")
            return render(request, "authentication_index.html", {"form": form})

        # Choose dashboard from POSITION
        position_norm = _primary_staff_position(user_payload)   # e.g., "BARANGAY CLERK"
        default_target = _dashboard_for_position(position_norm)

        # Honor safe next
        next_param = request.POST.get("next") or request.GET.get("next")
        target = _safe_next(request, next_param) or default_target

        # Store your session payload
        # (No Django auth login; you control access with a custom decorator.)
        request.session.flush()  # drop any old session id/contents (anti-fixation)
        request.session["user"] = user_payload
        request.session["role"] = user_payload.get("role")
        request.session["position"] = user_payload.get("position")
        request.session.modified = True

        # Debug ONLY — remove in production
        print("Session data:", dict(request.session))

        # Prepare response + set API cookies if tokens exist
        resp = redirect(target)
        if access and refresh:
            set_auth_cookies(resp, access, refresh)

        # Prime CSRF (optional)
        get_token(request)
        return resp

    # GET
    return render(request, "authentication_index.html", {"form": LoginForm()})


def logout(request):
    """
    Clear session and auth cookies.
    """
    from .cookie_utils import clear_auth_cookies

    resp = redirect("login")  # or your login URL name
    request.session.flush()
    clear_auth_cookies(resp)
    return resp


def debug_session(request):
    """
    (Optional) Debug helper to inspect session in browser.
    Protect this behind staff_login_required or remove in production.
    """
    from django.http import JsonResponse
    user = request.session.get("user")
    if not user:
        return JsonResponse({"error": "not logged in"}, status=401)
    return JsonResponse(dict(request.session))


# def login(request):
#     if request.method == "POST":
#         form = LoginForm(request.POST)
#         if form.is_valid():
#             username = form.cleaned_data["email_username"].strip()
#             password = form.cleaned_data["password"]

#             api_url = "http://192.168.1.4:8000/api/auth/login/"  # make sure this is correct
#             print("[WEB] Calling API:", api_url)
#             print("[WEB] Payload:", {"username": username, "password": "***"})

#             try:
#                 r = requests.post(
#                     api_url,
#                     json={"username": username, "password": password},
#                     headers={"Accept": "application/json", "Content-Type": "application/json"},
#                     timeout=10,
#                 )
#                 print("[WEB] API status:", r.status_code)
#                 print("[WEB] Raw response (first 500 chars):", r.text[:500])
#                 r.raise_for_status()
#             except requests.RequestException as e:
#                 print("[WEB] API request failed:", e)
#                 form.add_error(None, f"Login service is unreachable: {e}")
#             else:
#                 try:
#                     data = r.json()
#                 except ValueError:
#                     print("[WEB] Response not JSON decodable")
#                     form.add_error(None, "Unexpected response from login service.")
#                 else:
#                     token = data.get("token")
#                     user  = data.get("user")
#                     print("[WEB] Parsed JSON user:", user)
#                     print("[WEB] Token (first 40 chars):", (token[:40] + "...") if token else None)

#                     # Save session
#                     request.session["user"] = user
#                     request.session["auth_token_present"] = bool(token)
#                     request.session.save()
#                     print("[WEB] Session key:", request.session.session_key)
#                     print("[WEB] Session data now:", dict(request.session))

#                     # Redirect + set cookie
#                     return redirect("clerk:review_request")
#     else:
#         form = LoginForm()

#     return render(request, "authentication_index.html", {"form": form})




# def forgot_password(request):
#     form = ForgotPasswordForm()

#     return render(request, "forgot_password.html", {
#         'form': form,

#     })

# def new_password(request):
#     form = NewPasswordForm()
    
#     return render(request, "new_password.html", {
#         'form' : form,
#     })

# def email_sent(request):
#     return render(request, "email_sent.html")

# def email_confirmed(request):
#     return render(request, "email_confirmed.html")

# def temporary_password(request):
#     return render(request, 'temporary_password.html', {
#         'user_fullname': user_fullname,
#         'user_role': user_role,
#         'page_path': f'{user_role} / User Registration Log / Temporary Password',
#         'page_title': 'Temporary Password',
#         'user_role_template': user_role_template,
#     })




from pypdf import PdfReader

def testPdf(request):
    reader = PdfReader("barangay-residency.pdf")
    fields = reader.get_form_text_fields()
    print(fields)

def list_form_fields(pdf_path: str) -> dict:
    reader = PdfReader(pdf_path)
    fields = {}
    if "/AcroForm" in reader.trailer["/Root"]:
        form = reader.trailer["/Root"]["/AcroForm"]
        if "/Fields" in form:
            for f in form["/Fields"]:
                obj = f.get_object()
                name = obj.get("/T")
                if name:
                    fields[name] = obj
    return fields

    reader = PdfReader("barangay-residency.pdf")
    fields = reader.get_form_text_fields()
    print(fields)