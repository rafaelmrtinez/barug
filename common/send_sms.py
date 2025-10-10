# common/send_sms.py
from __future__ import annotations

import os
import json
import time
from types import SimpleNamespace
from typing import Iterable, List, Optional, Union

import requests
from dotenv import load_dotenv

load_dotenv()

SEMAPHORE_API_KEY = os.getenv("SEMAPHORE_API_KEY", "")
SEMAPHORE_SENDER_NAME = os.getenv("SEMAPHORE_SENDER_NAME", "SEMAPHORE")
SEMAPHORE_URL = os.getenv("SEMAPHORE_URL", "https://api.semaphore.co/api/v4/messages")
SEMAPHORE_TIMEOUT = float(os.getenv("SEMAPHORE_TIMEOUT", "10"))  # seconds

def _normalize_ph_number(msisdn: str) -> str:
    """
    Accepts: 09171234567, +639171234567, 639171234567
    Returns E.164: 639171234567
    """
    if not msisdn:
        return msisdn
    msisdn = "".join(ch for ch in msisdn if ch.isdigit() or ch == "+")
    if msisdn.startswith("+"):
        msisdn = msisdn[1:]
    if msisdn.startswith("09"):
        return f"63{msisdn[1:]}"
    if msisdn.startswith("9") and len(msisdn) == 10:
        return f"63{msisdn}"
    if msisdn.startswith("63"):
        return msisdn
    # Fallback: return as-is (Semaphore will reject if invalid)
    return msisdn

def send_sms(
    to: Union[str, Iterable[str]],
    message: str,
    *,
    sender_name: Optional[str] = None,
    fail_silently: bool = False,
    dry_run: bool = False,
    throttle_per_sec: float = 0.0,
) -> SimpleNamespace:
    """
    Send an SMS using Semaphore.
    Returns: SimpleNamespace(ok, status, data, detail, error_code)
    """
    try:
        api_key = SEMAPHORE_API_KEY
        if not api_key:
            raise RuntimeError("SEMAPHORE_API_KEY is not set")

        sender = sender_name or SEMAPHORE_SENDER_NAME or "SEMAPHORE"

        # Normalize recipients
        if isinstance(to, str):
            numbers: List[str] = [_normalize_ph_number(to)]
        else:
            numbers = [_normalize_ph_number(x) for x in to]

        numbers = [n for n in numbers if n]  # drop empties
        if not numbers:
            raise ValueError("No recipient numbers provided")

        payload_base = {
            "apikey": api_key,
            "message": message,
            "sendername": sender,
        }

        if dry_run:
            return SimpleNamespace(
                ok=True,
                status=200,
                data=[{"number": n, "status": "Queued", "dry_run": True} for n in numbers],
                detail="dry_run",
                error_code=None,
            )

        # --- helper to call API once
        def _post(data: dict) -> tuple[int, object, str | None, int | None]:
            resp = requests.post(SEMAPHORE_URL, data=data, timeout=SEMAPHORE_TIMEOUT)
            status = resp.status_code
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}
            # Extract common error/detail
            detail = None
            code = None
            if isinstance(body, dict):
                # v4 error shape
                detail = body.get("error") or body.get("message")
                code = body.get("code")
                # Field-level errors (e.g., {"number":["The number field is required."]})
                if not detail:
                    # flatten first field error for visibility
                    for k, v in body.items():
                        if isinstance(v, list) and v and isinstance(v[0], str):
                            detail = f"{k}: {v[0]}"
                            break
            return status, body, detail, code

        CHUNK = 900
        all_results = []

        for i in range(0, len(numbers), CHUNK):
            chunk = numbers[i:i+CHUNK]

            # Primary shape:
            #  - single  => "number"
            #  - multiple => "numbers" (comma-separated)
            if len(chunk) == 1:
                data = {**payload_base, "number": chunk[0]}
            else:
                data = {**payload_base, "numbers": ",".join(chunk)}

            status, body, detail, code = _post(data)

            # Success when HTTP 2xx AND body is a list of message receipts
            if 200 <= status < 300 and isinstance(body, list):
                all_results.extend(body)
            else:
                # Retry with alternative shapes if it looks like a param error
                retried = False
                # Try numbers[] form for bulk
                if len(chunk) > 1:
                    alt = {**payload_base, "numbers[]": chunk}
                    status2, body2, detail2, code2 = _post(alt)
                    retried = True
                    if 200 <= status2 < 300 and isinstance(body2, list):
                        all_results.extend(body2)
                    else:
                        # Try per-number single sends (last resort)
                        indiv_results = []
                        ok_all = True
                        for n in chunk:
                            status3, body3, detail3, code3 = _post({**payload_base, "number": n})
                            if 200 <= status3 < 300 and isinstance(body3, list):
                                indiv_results.extend(body3)
                            else:
                                ok_all = False
                                # Keep first visible error
                                if not detail:
                                    detail = detail3 or str(body3)
                                if code is None:
                                    code = code3
                        if ok_all and indiv_results:
                            all_results.extend(indiv_results)
                        else:
                            if fail_silently:
                                return SimpleNamespace(ok=False, status=status2, data=body2, detail=detail2 or detail, error_code=code2 or code)
                            raise RuntimeError(f"Semaphore SMS failed: {detail2 or detail} (status {status2}, code={code2 or code})")
                else:
                    # Single number failed — try with 'numbers' just in case
                    alt = {**payload_base, "numbers": chunk[0]}
                    status2, body2, detail2, code2 = _post(alt)
                    retried = True
                    if 200 <= status2 < 300 and isinstance(body2, list):
                        all_results.extend(body2)
                    else:
                        if fail_silently:
                            return SimpleNamespace(ok=False, status=status2, data=body2, detail=detail2 or detail, error_code=code2 or code)
                        raise RuntimeError(f"Semaphore SMS failed: {detail2 or detail} (status {status2}, code={code2 or code})")

            if throttle_per_sec and (i + CHUNK) < len(numbers):
                time.sleep(throttle_per_sec)

        return SimpleNamespace(ok=True, status=200, data=all_results, detail=None, error_code=None)

    except Exception as e:
        if not fail_silently:
            raise
        return SimpleNamespace(ok=False, status=0, data=None, detail=str(e), error_code=None)


def send_otp(
    to: Union[str, Iterable[str]],
    otp_code: str,
    *,
    app_name: str = "Barug",
    expire_minutes: int = 10,
    **kwargs,
) -> SimpleNamespace:
    """
    Convenience wrapper for OTP-style messages.
    """
    msg = f"{app_name} OTP: {otp_code}\nThis code expires in {expire_minutes} minutes. Do not share this with anyone."
    return send_sms(to, msg, **kwargs)
