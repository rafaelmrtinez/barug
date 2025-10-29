def _pg_err_tuple(err):
    """Return (pgcode, primary_message) from a Django/psycopg error."""
    for obj in (err, getattr(err, "__cause__", None), getattr(err, "__context__", None)):
        if not obj:
            continue
        pgcode = getattr(obj, "pgcode", None)
        diag   = getattr(obj, "diag", None)
        primary = getattr(diag, "message_primary", None) if diag else None
        if pgcode or primary:
            return pgcode, (primary.strip() if isinstance(primary, str) else None)
    # fallback
    return None, (str(err) or None)