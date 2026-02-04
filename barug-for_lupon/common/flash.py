# common/flash.py
from __future__ import annotations
import logging
import re
from django.contrib import messages
from django.db import DatabaseError, OperationalError, IntegrityError

logger = logging.getLogger(__name__)

SYSTEM_OOPS = "Oops! Our system is having an issue for now. Please try again later."

def _extract_psycopg_diag(err):
    """Return (pgcode, primary_message) if available; else (None, trimmed_text)."""
    def _parse_pgerror_text(pgerr: str) -> str | None:
        if not pgerr:
            return None
        try:
            lines = [l.strip() for l in str(pgerr).splitlines() if l.strip()]
            if not lines:
                return None
            # Look for a line starting with ERROR: and strip common trailing sections
            for ln in lines:
                if ln.upper().startswith("ERROR:"):
                    # Remove leading 'ERROR:' and stop at DETAIL:/CONTEXT:/LOCATION:
                    s = ln.split("ERROR:", 1)[1]
                    s = re.split(r"DETAIL:|CONTEXT:|LOCATION:", s, flags=re.IGNORECASE)[0].strip()
                    return s or None
            # Fallback: return first non-empty line without further parsing
            return lines[0]
        except Exception:
            return None

    for obj in (err, getattr(err, "__cause__", None), getattr(err, "__context__", None)):
        if not obj:
            continue
        pgcode = getattr(obj, "pgcode", None)
        diag = getattr(obj, "diag", None)
        primary = getattr(diag, "message_primary", None) if diag else None
        if primary and isinstance(primary, str) and primary.strip():
            return pgcode, primary.strip()

        # Some drivers (psycopg2) expose the raw server text in pgerror
        pgerr = getattr(obj, "pgerror", None)
        parsed = _parse_pgerror_text(pgerr)
        if parsed:
            return pgcode, parsed

        # As a last resort check the exception args for a textual message
        args = getattr(obj, "args", None)
        if args and len(args) > 0 and isinstance(args[0], str):
            parsed_args = _parse_pgerror_text(args[0]) or args[0].strip()
            if parsed_args:
                return pgcode, parsed_args

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
        # If we can extract a primary message from the DB/trigger, show it to the user.
        # This helps surfacing trigger-raised errors (e.g. RAISE EXCEPTION ...) even
        # when they don't use our custom pgcode range.
        if primary:
            # Keep it short/safe for display
            primary_safe = str(primary).strip()
            if len(primary_safe) > 1000:
                primary_safe = primary_safe[:1000] + "..."
            messages.error(request, primary_safe)
        else:
            messages.error(request, SYSTEM_OOPS)

        # Log the full exception for debugging. Guard the logging call so that
        # a console encoding error (common on Windows consoles) doesn't raise
        # and disrupt request handling.
        try:
            logger.exception("Database error", exc_info=err)
        except Exception as log_exc:
            # Try a fallback ascii-only log
            try:
                logger.error("Database error (logging failed): %s", str(log_exc))
            except Exception:
                # Best-effort: ignore to avoid raising from the error handler
                pass
    except Exception:
        # If extraction or logging failed, ensure we still show a friendly message
        try:
            logger.error("Database error (extract failed)", exc_info=err)
        except Exception:
            pass
        messages.error(request, SYSTEM_OOPS)

def flash_system_error(request, log_msg: str, *, exc: Exception | None = None) -> None:
    if exc:
        logger.exception(log_msg)
    else:
        logger.error(log_msg)
    messages.error(request, SYSTEM_OOPS)
