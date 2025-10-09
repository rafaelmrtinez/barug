from .generic import GenericAcroHandler
from .kp7 import KP7Handler
from .kp9 import KP9Handler  # <-- add

# Map form_code → handler instance
_REGISTRY = {
    "KP-7": KP7Handler(),
    "KP-9": KP9Handler(),    # <-- register KP-9
    # Add more: "KP-12": KP12Handler(), etc.
}

def get_handler(form_code: str):
    """
    Return a specialized handler if registered; otherwise the generic handler.
    """
    return _REGISTRY.get(form_code, GenericAcroHandler())
