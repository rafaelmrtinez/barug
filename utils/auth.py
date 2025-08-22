# utils/auth.py
from rest_framework_simplejwt.tokens import AccessToken

def get_uid_from_request(request) -> int | None:
    token = request.COOKIES.get('access')
    if not token:
        return None
    try:
        at = AccessToken(token)   # validates & decodes
        return at.get('uid')
    except Exception:
        return None
