import requests
from django.core.mail import send_mail
from django.conf import settings

SUPABASE_URL = settings.SUPABASE_URL.rstrip("/")
SRK = settings.SUPABASE_SERVICE_ROLE_KEY

ADMIN_HEADERS = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
}

def _send_html_email(to_email: str, subject: str, html: str) -> None:
    send_mail(
        subject,
        "",  # plain-text fallback
        settings.EMAIL_HOST_USER,
        [to_email],
        fail_silently=False,
        html_message=html,
    )

def send_signup_confirmation_link(email: str) -> bool:
    """
    Resend verification to an existing user, or generate a signup link for new users.
    - NEW user: admin/generate_link(type='signup') -> we send our own email
    - EXISTING & unverified: admin/resend(type='signup') -> Supabase sends email
    - EXISTING & verified: generate a magic link so they can sign in
    Returns True if an email was sent (by us or Supabase), False otherwise.
    """
    # 1) Try to generate a signup confirmation link (works only for NEW users)
    gen_resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers=ADMIN_HEADERS,
        json={"type": "signup", "email": email},
        timeout=20,
    )

    if gen_resp.status_code in (200, 201):
        action_link = (gen_resp.json() or {}).get("action_link", "").replace("\\u0026", "&")
        if not action_link:
            return False
        html = f"""
            <h1>Confirm Your BaRUG Account</h1>
            <p>Hello,</p>
            <p>Click the button below to confirm your email address and activate your BaRUG account:</p>
            <p><a href="{action_link}" style="padding:10px 20px;background:#007bff;color:white;text-decoration:none;border-radius:5px;">Confirm Email</a></p>
            <p>If you didn’t request this, you can safely ignore it.</p>
        """
        _send_html_email(email, "Confirm Your BaRUG Account", html)
        return True

    data = {}
    try:
        data = gen_resp.json()
    except Exception:
        pass

    # 2) If the user already exists, use the **resend** admin endpoint
    if gen_resp.status_code == 422 and (data.get("error_code") == "email_exists" or data.get("msg") == "A user with this email address has already been registered"):
        resend_resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/admin/resend",
            headers=ADMIN_HEADERS,
            json={"type": "signup", "email": email},
            timeout=20,
        )
        # Supabase sends the verification email itself for this case
        if resend_resp.status_code in (200, 201, 204):
            return True

        # 3) If resend fails (likely the user is already verified), fall back to a magic link
        magic_resp = requests.post(
            f"{SUPABASE_URL}/auth/v1/admin/generate_link",
            headers=ADMIN_HEADERS,
            json={"type": "magiclink", "email": email},
            timeout=20,
        )
        if magic_resp.status_code in (200, 201):
            action_link = (magic_resp.json() or {}).get("action_link", "").replace("\\u0026", "&")
            if not action_link:
                return False
            html = f"""
                <h1>Confirm Your BaRUG Account</h1>
                <p>Hello,</p>
                <p>Click the button below to confirm your email address and activate your BaRUG account:</p>
                <p><a href="{action_link}" style="padding:10px 20px;background:#10b981;color:white;text-decoration:none;border-radius:5px;">Sign in</a></p>
            """
            _send_html_email(email, "Sign in to BaRUG", html)
            return True

        # Couldn’t resend or generate magic link
        return False

    # Other error (network, bad config, etc) — don’t 500 your API; just return False
    return False


def verify_email_deliverable_abstract(email: str) -> tuple[bool, str]:
    """
    Check if an email is deliverable using AbstractAPI.
    Returns (ok, reason).
    - ok=False only when deliverability is UNDELIVERABLE.
    - Fail-open on API/network issues so you don't block signups if provider is down.
    """

    key = getattr(settings, "ABSTRACT_EMAIL_KEY", "")
    if not key:
        return True, "no_api_key_configured"

    try:
        r = requests.get(
            "https://emailvalidation.abstractapi.com/v1/",
            params={"api_key": key, "email": email},
            timeout=10,
        )
        data = r.json()

        # AbstractAPI field of interest
        status = (data.get("deliverability") or "").upper()  # DELIVERABLE | UNDELIVERABLE | RISKY | UNKNOWN

        if status == "UNDELIVERABLE":
            return False, "UNDELIVERABLE"

        # treat DELIVERABLE, RISKY, UNKNOWN as acceptable
        return True, status or "UNKNOWN"

    except Exception as e:
        # Fail-open: allow signups if API fails
        return True, f"verify_error:{e}"
