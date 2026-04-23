from functools import wraps
from django.utils.cache import add_never_cache_headers

def nocache(view_func):
    """Decorator that adds headers to prevent browser caching."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response
    return _wrapped_view
