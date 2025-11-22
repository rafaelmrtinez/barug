from django import template

register = template.Library()

def _flatten_choices(choices):
    """Flattens choices/optgroups into a simple [(value, label), ...] list."""
    flat = []
    for c in list(choices or []):
        # Optgroup: (group_label, [(val, label), ...])
        if isinstance(c[1], (list, tuple)):
            for opt in c[1]:
                flat.append((str(opt[0]), str(opt[1])))
        else:
            flat.append((str(c[0]), str(c[1])))
    return flat

@register.filter
def format_mobile(mobile_number):
    """
    Format mobile number to start with +639.
    Handles various input formats:
    - 09123456789 -> +639123456789
    - 9123456789 -> +639123456789
    - +639123456789 -> +639123456789 (no change)
    - 639123456789 -> +639123456789
    """
    if not mobile_number:
        return ""
    
    # Convert to string and remove any spaces or dashes
    mobile = str(mobile_number).strip().replace(" ", "").replace("-", "")
    
    # If already starts with +639, return as is
    if mobile.startswith("+639"):
        return mobile
    
    # If starts with 639, add +
    if mobile.startswith("639"):
        return "+" + mobile
    
    # If starts with 09, replace with +639
    if mobile.startswith("09"):
        return "+639" + mobile[2:]
    
    # If starts with 9 and is 10 digits, add +63
    if mobile.startswith("9") and len(mobile) == 10:
        return "+63" + mobile
    
    # Return original if format is unrecognized
    return mobile_number

@register.filter
def choice_label(bound_field, raw_value):
    """
    Usage in template:
      {% load choice_extras %}
      {% with label=form.b_type|choice_label:request.GET.b_type %}{{ label }}{% endwith %}

    Works for ChoiceField/ModelChoiceField and MultiChoice fields.
    - bound_field: e.g., form.b_type
    - raw_value:   e.g., request.GET.b_type (string) or list for multiple
    """
    # If someone passes the Field instead of BoundField, handle gracefully
    field = getattr(bound_field, "field", bound_field)
    choices = getattr(field, "choices", None)
    if not choices:
        return ""

    flat = _flatten_choices(choices)

    # Multi-select?
    widget = getattr(field, "widget", None)
    allow_multi = bool(getattr(widget, "allow_multiple_selected", False))

    if allow_multi:
        # Accept comma-separated string OR list
        if isinstance(raw_value, str):
            values = [v for v in raw_value.split(",") if v != ""]
        elif isinstance(raw_value, (list, tuple, set)):
            values = list(raw_value)
        else:
            values = [str(raw_value)] if raw_value is not None else []

        values = set(map(str, values))
        labels = [label for (val, label) in flat if str(val) in values]
        return ", ".join(labels)
    else:
        target = "" if raw_value is None else str(raw_value)
        for val, label in flat:
            if str(val) == target:
                return label
        return ""
