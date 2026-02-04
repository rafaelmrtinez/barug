import requests
from django.core.mail import send_mail
from django.conf import settings

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