# notifications/services.py
from .twilio_sms import send_twilio_sms

APPROVED_TMPL = (
    "Your document request {ref_no} has been APPROVED. "
    "Please proceed to the Barangay Office to finalize the transaction and receive your document."
)
REJECTED_TMPL = (
    "Your document request {ref_no} was REJECTED. "
    "{reason}If you have questions, please contact the Barangay Office."
)

def send_doc_status_sms(to_number: str, ref_no: str, status: str, reason: str = "") -> tuple[bool, str]:
    status = status.upper()
    if status == "APPROVED":
        body = APPROVED_TMPL.format(ref_no=ref_no)
    elif status == "REJECTED":
        reason_txt = f"Reason: {reason}. " if reason else ""
        body = REJECTED_TMPL.format(ref_no=ref_no, reason=reason_txt)
    else:
        return False, "Unsupported status"
    return send_twilio_sms(to_number, body)
