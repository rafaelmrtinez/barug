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
    throttle_per_sec: float = 0.0,  # simple throttle between requests if sending individually
) -> SimpleNamespace:
    """
    Send an SMS using Semaphore.

    Args:
      to: single number or list/iterable of numbers
      message: text content
      sender_name: overrides SEMAPHORE_SENDER_NAME
      fail_silently: swallow exceptions and return ok=False instead of raising
      dry_run: if True, skip HTTP call (for tests); returns ok=True with mocked data
      throttle_per_sec: sleep seconds between chunked calls (if very large batches)

    Returns:
      SimpleNamespace(ok, status, data, detail, error_code)
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

        if not numbers:
            raise ValueError("No recipient numbers provided")

        # Semaphore accepts either single "number" or multiple "numbers[]"
        payload = {
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

        # If <= 1000 numbers, we can send as one call using numbers[]
        # (Semaphore supports bulk via numbers[]). For very large sets, chunk.
        CHUNK = 900
        all_results = []
        for i in range(0, len(numbers), CHUNK):
            chunk = numbers[i : i + CHUNK]
            data = payload.copy()
            if len(chunk) == 1:
                data["number"] = chunk[0]
            else:
                # multiple — use repeated key 'numbers[]'
                # requests handles list expansion automatically if we pass list at that key
                data["numbers[]"] = chunk

            resp = requests.post(SEMAPHORE_URL, data=data, timeout=SEMAPHORE_TIMEOUT)
            status = resp.status_code

            # Semaphore returns JSON array on success; error has {"error":"...", "code":...}
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}

            if status >= 200 and status < 300 and isinstance(body, list):
                all_results.extend(body)
            else:
                # Error shape
                detail = body.get("error") if isinstance(body, dict) else str(body)
                code = body.get("code") if isinstance(body, dict) else None
                if fail_silently:
                    return SimpleNamespace(ok=False, status=status, data=body, detail=detail, error_code=code)
                raise RuntimeError(f"Semaphore SMS failed: {detail} (status {status}, code={code})")

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
