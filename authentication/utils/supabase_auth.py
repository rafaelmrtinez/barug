# utils/supabase_auth.py

import requests
from django.conf import settings

def delete_supabase_user(user_id):
    # [DEBUG] print(f"🧹 Attempting to delete Supabase user: {user_id}")
    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    }

    try:
        response = requests.delete(url, headers=headers)
        # [DEBUG] print(f"🔧 DELETE status: {response.status_code}")
        # [DEBUG] print(f"📦 DELETE response: {response.text}")
        return response.status_code
    except Exception as e:
        print(f"🔥 Error deleting user from Supabase: {str(e)}")
        return 500


def verify_email_deliverable_abstract(email: str) -> tuple[bool, str]:
    """
    Returns (ok, reason). ok=False only when clearly undeliverable.
    Fail-open on network/API issues so you don't block signups if provider is down.
    """
    key = getattr(settings, "ABSTRACT_EMAIL_KEY", "")
    if not settings.EMAIL_VERIFY_ENABLE or not key:
        return True, "skipped"

    try:
        r = requests.get(
            "https://emailvalidation.abstractapi.com/v1/",
            params={"api_key": key, "email": email},
            timeout=10,
        )
        data = r.json()
        status = (data.get("deliverability") or "").upper()  # DELIVERABLE | UNDELIVERABLE | RISKY | UNKNOWN
        # Treat RISKY/UNKNOWN as OK to avoid false blocks on catch-all domains
        if status == "UNDELIVERABLE":
            return False, "UNDELIVERABLE"
        return True, status or "UNKNOWN"
    except Exception as e:
        return True, f"verify_error:{e}"