from django.utils.cache import add_never_cache_headers
from .profile import get_person_profile
from django.utils.cache import add_never_cache_headers

class NoCacheMiddleware:
    """Prevent browsers from caching pages."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        add_never_cache_headers(response)
        return response


class AttachProfileMiddleware:
    """
    If session contains person_id, attach the profile to request.person_profile.
    Also add no-store headers so back-button won't show cached protected pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth = request.session.get("auth") or {}
        person_id = auth.get("person_id")
        request.person_profile = None
        if person_id:
            request.person_profile = get_person_profile(person_id)

        response = self.get_response(request)
        add_never_cache_headers(response)
        return response