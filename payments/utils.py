import base64, hmac, hashlib, time
from django.conf import settings

def paymongo_auth_header():
    # PayMongo expects HTTP Basic auth with your secret key
    token = base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def verify_paymongo_signature(raw_body: bytes, signature_header: str, tolerance=300) -> bool:
    """
    signature_header looks like: 't=169... , v1=<hex>'
    We compute HMAC_SHA256(secret, f"{t}.{raw_body}") and compare to v1.
    """
    try:
        parts = dict(p.strip().split('=') for p in signature_header.split(','))
        t  = int(parts.get('t'))
        v1 = parts.get('v1')
    except Exception:
        return False

    payload = f"{t}.{raw_body.decode('utf-8')}".encode('utf-8')
    secret  = settings.PAYMONGO_WEBHOOK_SECRET.encode('utf-8')
    digest  = hmac.new(secret, payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(digest, v1 or ""):
        return False

    # basic replay guard
    if abs(time.time() - t) > tolerance:
        return False

    return True
