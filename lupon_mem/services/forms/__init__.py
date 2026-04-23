# lupon_mem/services/forms/__init__.py

from lupon_mem.services.forms.generic import GenericAcroHandler

# Existing KP handlers
from lupon_mem.services.forms.kp7 import KP7Handler
from lupon_mem.services.forms.kp8 import KP8Handler
from lupon_mem.services.forms.kp9 import KP9Handler
from lupon_mem.services.forms.kp10 import KP10Handler
from lupon_mem.services.forms.kp11 import KP11Handler
from lupon_mem.services.forms.kp12 import KP12Handler
from lupon_mem.services.forms.kp13 import KP13Handler
from lupon_mem.services.forms.kp14 import KP14Handler
from lupon_mem.services.forms.kp15 import KP15Handler
from lupon_mem.services.forms.kp16 import KP16Handler
from lupon_mem.services.forms.kp17 import KP17Handler
from lupon_mem.services.forms.kp18 import KP18Handler
from lupon_mem.services.forms.kp19 import KP19Handler
from lupon_mem.services.forms.kp20 import KP20Handler

# NEW: KP-20A..KP-25 handlers you added
from lupon_mem.services.forms.kp20a import KP20AHandler
from lupon_mem.services.forms.kp20b import KP20BHandler
from lupon_mem.services.forms.kp21 import KP21Handler
from lupon_mem.services.forms.kp22 import KP22Handler
from lupon_mem.services.forms.kp23 import KP23Handler
from lupon_mem.services.forms.kp24 import KP24Handler
from lupon_mem.services.forms.kp25 import KP25Handler

# NEW: non-KP forms you added in SQL
from lupon_mem.services.forms.ack_receipt import AckReceiptHandler
from lupon_mem.services.forms.case_folder import CaseFolderHandler
from lupon_mem.services.forms.invitation import InvitationHandler
from lupon_mem.services.forms.lupon_blotter import LuponBlotterHandler
from lupon_mem.services.forms.med_attendance_2025 import MedAttendance2025Handler
from lupon_mem.services.forms.minutes import MinutesHandler
from lupon_mem.services.forms.monitoring_complainant import MonitoringComplainantHandler
from lupon_mem.services.forms.monitoring_respondent import MonitoringRespondentHandler
from lupon_mem.services.forms.med1_settled import Med1SettledHandler
from lupon_mem.services.forms.med2_fta_set import Med2FtaSettledHandler
from lupon_mem.services.forms.med2_settled import Med2SettledHandler
from lupon_mem.services.forms.med3_folder import Med3FolderHandler
from lupon_mem.services.forms.med3_settled import Med3SettledHandler
from lupon_mem.services.forms.kp9_2 import KP9_2Handler

# Map form_code → handler instance
_REGISTRY = {
    # KP (existing)
    "KP-7":   KP7Handler(),
    "KP-8":   KP8Handler(),
    "KP-9":   KP9Handler(),
    "KP-9-P2": KP9_2Handler(),  # KP-9 Officer's Return (Page 2)
    "KP-10":  KP10Handler(),
    "KP-11":  KP11Handler(),
    "KP-12":  KP12Handler(),
    "KP-13":  KP13Handler(),
    "KP-14":  KP14Handler(),
    "KP-15":  KP15Handler(),
    "KP-16":  KP16Handler(),
    "KP-17":  KP17Handler(),
    "KP-18":  KP18Handler(),
    "KP-19":  KP19Handler(),
    "KP-20":  KP20Handler(),

    # KP (newly added)
    "KP-20A": KP20AHandler(),
    "KP-20B": KP20BHandler(),
    "KP-21":  KP21Handler(),
    "KP-22":  KP22Handler(),
    "KP-23":  KP23Handler(),
    "KP-24":  KP24Handler(),
    "KP-25":  KP25Handler(),

    # Non-KP forms (new)
    "ACK-RECEIPT":   AckReceiptHandler(),
    "CASE-FOLDER":   CaseFolderHandler(),
    "INVITATION":    InvitationHandler(),
    "LUPON-BLOTTER": LuponBlotterHandler(),
    "MED-ATT-2025":  MedAttendance2025Handler(),
    "MINUTES":       MinutesHandler(),
    "MON-COMPL":     MonitoringComplainantHandler(),
    "MON-RESP":      MonitoringRespondentHandler(),
    "MED1-SETTLED":  Med1SettledHandler(),
    "MED2-FTA-SET":  Med2FtaSettledHandler(),
    "MED2-SETTLED":  Med2SettledHandler(),
    "MED3-FOLDER":   Med3FolderHandler(),
    "MED3-SETTLED":  Med3SettledHandler(),
}

def get_handler(form_code: str):
    """Return a specialized handler if registered; otherwise the generic handler."""
    return _REGISTRY.get(form_code, GenericAcroHandler())
