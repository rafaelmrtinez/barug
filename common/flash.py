# common/flash.py
from __future__ import annotations
import logging
from django.contrib import messages
from django.db import DatabaseError, OperationalError, IntegrityError

logger = logging.getLogger(__name__)

SYSTEM_OOPS = "Oops! Our system is having an issue for now. Please try again later."

def _extract_psycopg_diag(err):
    """Return (pgcode, primary_message) if available; else (None, trimmed_text)."""
    for obj in (err, getattr(err, "__cause__", None), getattr(err, "__context__", None)):
        if not obj:
            continue
        pgcode = getattr(obj, "pgcode", None)
        diag   = getattr(obj, "diag", None)
        primary = getattr(diag, "message_primary", None) if diag else None
        if pgcode or primary:
            return pgcode, (primary.strip() if isinstance(primary, str) else None)

    txt = (str(err) or "").strip()
    if "CONTEXT:" in txt:
        txt = txt.split("CONTEXT:")[0].strip()
    return None, (txt or None)

def _is_custom_pgcode(pgcode: str | None) -> bool:
    """Custom codes are P5001..P6200 (inclusive)."""
    if not isinstance(pgcode, str) or not pgcode:
        return False
    if pgcode[0].upper() != "P":
        return False
    try:
        n = int(pgcode[1:])
    except Exception:
        return False
    return 5001 <= n <= 6200

# ---- Message helpers ----
def flash_success(request, text: str) -> None:
    messages.success(request, text)

def flash_warning(request, text: str) -> None:
    messages.warning(request, text)

def flash_db_error(request, err: Exception) -> None:
    """
    Show only our custom DB messages (P5001–P6200). Otherwise, show a friendly generic.
    Always log the full error for debugging.
    """
    try:
        pgcode, primary = _extract_psycopg_diag(err)
        if _is_custom_pgcode(pgcode) and primary:
            messages.error(request, primary)
        else:
            messages.error(request, SYSTEM_OOPS)
        logger.exception("Database error", exc_info=err)
    except Exception:
        logger.exception("Database error (extract failed)", exc_info=err)
        messages.error(request, SYSTEM_OOPS)

def flash_system_error(request, log_msg: str, *, exc: Exception | None = None) -> None:
    if exc:
        logger.exception(log_msg)
    else:
        logger.error(log_msg)
    messages.error(request, SYSTEM_OOPS)
