"""
Cached Bootstrap Icons Template Tag
Wraps django-bootstrap-icons with caching to dramatically improve performance
"""
from django import template
from django.core.cache import cache
from django_bootstrap_icons.templatetags.bootstrap_icons import bs_icon as original_bs_icon

register = template.Library()

@register.simple_tag
def bs_icon_cached(icon_name, size='1em', color=None, extra_classes=''):
    """
    Cached version of bs_icon that stores rendered SVG in cache
    Cache key includes all parameters to ensure correct rendering
    """
    # Create unique cache key based on all parameters
    cache_key = f"bs_icon_{icon_name}_{size}_{color}_{extra_classes}"
    
    # Try to get from cache
    cached_svg = cache.get(cache_key)
    if cached_svg:
        return cached_svg
    
    # If not in cache, render and store
    svg = original_bs_icon(icon_name, size=size, color=color, extra_classes=extra_classes)
    
    # Cache for 1 hour (icons don't change)
    cache.set(cache_key, svg, 3600)
    
    return svg
