from lupon_mem.services.forms.generic import GenericAcroHandler
from lupon_mem.services.forms.kp7 import KP7Handler
from lupon_mem.services.forms.kp8 import KP8Handler
from lupon_mem.services.forms.kp9 import KP9Handler  # <-- add
from lupon_mem.services.forms.kp10 import KP10Handler  # <-- add
from lupon_mem.services.forms.kp11 import KP11Handler  # <-- add
from lupon_mem.services.forms.kp12 import KP12Handler  # <-- add
from lupon_mem.services.forms.kp13 import KP13Handler  # <-- add
from lupon_mem.services.forms.kp14 import KP14Handler  # <-- add
from lupon_mem.services.forms.kp15 import KP15Handler  # <-- add
from lupon_mem.services.forms.kp16 import KP16Handler  # <-- add
from lupon_mem.services.forms.kp17 import KP17Handler  # <-- add
# To be added
from lupon_mem.services.forms.kp18 import KP18Handler  # <-- add
# from lupon_mem.services.forms.kp19 import KP19Handler  # <-- add
# from lupon_mem.services.forms.kp20 import KP20Handler  # <-- add
# from lupon_mem.services.forms.kp21 import KP21Handler  # <-- add
# from lupon_mem.services.forms.kp22 import KP22Handler  # <-- add
# from lupon_mem.services.forms.kp23 import KP23Handler  # <-- add
# from lupon_mem.services.forms.kp24 import KP24Handler  # <-- add
# from lupon_mem.services.forms.kp25 import KP25Handler  # <-- add
# from lupon_mem.services.forms.kp26 import KP26Handler  # <-- add


# Map form_code → handler instance
_REGISTRY = {
    "KP-7": KP7Handler(),
    "KP-8": KP8Handler(),
    "KP-9": KP9Handler(),   
    "KP-10": KP10Handler(),  
    "KP-11": KP11Handler(),  
    "KP-12": KP12Handler(),  
    "KP-13": KP13Handler(),  
    "KP-14": KP14Handler(),  
    "KP-15": KP15Handler(),  
    "KP-16": KP16Handler(),  
    "KP-17": KP17Handler(),  
    "KP-18": KP18Handler(),  
    # "KP-19": KP19Handler(),
    # "KP-20": KP20Handler(),  
    # "KP-21": KP21Handler(),  
    # "KP-22": KP22Handler(),  
    # "KP-23": KP23Handler(),  
    # "KP-24": KP24Handler(),  
    # "KP-25": KP25Handler(),  
    # "KP-26": KP26Handler(),   
    # Add more: "KP-12": KPxxHandler(), etc.
}

def get_handler(form_code: str):
    """
    Return a specialized handler if registered; otherwise the generic handler.
    """
    return _REGISTRY.get(form_code, GenericAcroHandler())
