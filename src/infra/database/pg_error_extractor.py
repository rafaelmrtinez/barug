"""Postgres error extraction helper.

This module exposes PGErrorExtractor which provides a safe way to extract a
primary error message and PG error code from exceptions raised by psycopg2/Django
DB operations. It intentionally avoids exposing raw SQL, parameters or full
exception messages to the logs to reduce the risk of leaking secrets.
"""
from typing import Tuple, Optional


class PGErrorExtractor:
    """Helper to extract short, safe error info from DB exceptions.

    The method returns a tuple (message, pgcode). The returned message is
    intentionally conservative and should be suitable for propagation to
    higher-layer exception wrappers but not for logging raw SQL/params.
    """

    @staticmethod
    def extract(exc: Exception) -> Tuple[str, Optional[str]]:
        orig = getattr(exc, "__cause__", None)
        try:
            if orig is not None and hasattr(orig, "diag"):
                primary = getattr(orig.diag, "message_primary", None) or str(orig)
                code = getattr(orig, "pgcode", None)
                return primary, code
        except Exception:
            # Fall through to safe fallback.
            pass

        # Safe fallback: return the exception type name as message and no code.
        return str(type(exc).__name__), None
