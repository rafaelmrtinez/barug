from lupon_mem.services.forms.generic import GenericAcroHandler
from lupon_mem.services.forms.kp7 import KP7Handler
from lupon_mem.services.forms.kp9 import KP9Handler  # <-- add
from lupon_mem.services.forms.kp8 import KP8Handler

# Map form_code → handler instance
_REGISTRY = {
    "KP-7": KP7Handler(),
    "KP-9": KP9Handler(),    # <-- register KP-9
    "KP-8": KP8Handler(),
    # Add more: "KP-12": KP12Handler(), etc.
}

def get_handler(form_code: str):
    """
    Return a specialized handler if registered; otherwise the generic handler.
    """
    return _REGISTRY.get(form_code, GenericAcroHandler())
