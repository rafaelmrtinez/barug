# notifications/twilio_sms.py
import re
from twilio.rest import Client
from django.conf import settings

_client = Client(122, 122)

def to_e164_ph(num: str) -> str | None:
    if not num: return None
    d = re.sub(r"\D", "", num)
    if d.startswith("09") and len(d) == 11: return "+63" + d[1:]
    if d.startswith("9")  and len(d) == 10: return "+63" + d
    if d.startswith("63") and len(d) == 12: return "+" + d
    if num.startswith("+63") and len(d) == 12: return num
    return None

def send_twilio_sms(to: str, body: str) -> tuple[bool, str]:
    """Returns (ok, sid_or_error)"""
    if not to: return False, "Invalid PH number"
    try:
        msg = _client.messages.create(to=to, body=body, from_=settings.TWILIO_FROM)
        return True, msg.sid
    except Exception as e:
        return False, str(e)
