# utils/ratelimit_keys.py  (put this somewhere importable)
def rl_user_or_ip(group, request):
    """
    Prefer per-user limiting via DRF-authenticated user (uid/id/pk).
    Fall back to client IP when not authenticated.
    Signature must be (group, request) for django-ratelimit.
    """
    user = getattr(request, "user", None)
    uid = (
        getattr(user, "uid", None)
        or getattr(user, "id", None)
        or getattr(user, "pk", None)
    )
    if uid:
        return f"user:{uid}"
    return request.META.get("REMOTE_ADDR", "")
