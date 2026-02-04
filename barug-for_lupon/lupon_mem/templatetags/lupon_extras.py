from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    """
    Safely fetch d[key] in templates.
    Works whether answers dict uses str or int keys.
    """
    if d is None:
        return ""
    # Try both string and original key
    try:
        return d.get(str(key), d.get(key, ""))
    except AttributeError:
        # d is not a dict-like
        return ""
