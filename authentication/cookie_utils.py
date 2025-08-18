# authentication/cookie_utils.py
from django.conf import settings

def set_auth_cookies(response, access_token, refresh_token):
    response.set_cookie(
        key="access",
        value=str(access_token),
        httponly=True,
        secure=getattr(settings, "JWT_COOKIE_SECURE", True),
        samesite=getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
        max_age=15 * 60,
        path="/",
        domain=getattr(settings, "JWT_COOKIE_DOMAIN", None),
    )
    response.set_cookie(
        key="refresh",
        value=str(refresh_token),
        httponly=True,
        secure=getattr(settings, "JWT_COOKIE_SECURE", True),
        samesite=getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
        max_age=7 * 24 * 60 * 60,
        path="/",
        domain=getattr(settings, "JWT_COOKIE_DOMAIN", None),
    )

def clear_auth_cookies(response):
    response.delete_cookie(
        "access",
        path="/",
        domain=getattr(settings, "JWT_COOKIE_DOMAIN", None),
        samesite=getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
    )
    response.delete_cookie(
        "refresh",
        path="/",
        domain=getattr(settings, "JWT_COOKIE_DOMAIN", None),
        samesite=getattr(settings, "JWT_COOKIE_SAMESITE", "Lax"),
    )
