from django.core.cache import cache
from django.db import connection

CACHE_TTL = 300  # 5 minutes

def _fetch_profile_from_db(person_id: int | str) -> dict | None:
    """
    Calls your Supabase function get_specific_resident_profile(person_id)
    and returns a dict. Adjust unpacking to your function's return shape.
    """
    with connection.cursor() as cur:
        # If your function RETURNS TABLE(...): use SELECT * FROM ...
        cur.execute("SELECT * FROM get_specific_resident_full_profile(%s);", [person_id])
        row = cur.fetchone()
        if not row:
            return None

        # Map row → dict. If your function returns a single JSON column,
        # you can just return row[0]. Otherwise map columns by name:
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

def get_person_profile(person_id: int | str, *, force_refresh: bool = False) -> dict | None:
    key = f"profile:{person_id}"
    if not force_refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    profile = _fetch_profile_from_db(person_id)
    if profile is not None:
        cache.set(key, profile, CACHE_TTL)
    return profile

def invalidate_person_profile(person_id: int | str):
    cache.delete(f"profile:{person_id}")
