# authentication/services.py
from django.core.cache import cache
from django.db import connection

PROFILE_TTL = 60 * 5  # 5 minutes

def _db_get_resident_profile(user_id: int):
    """
    Calls your Postgres function. Adjust unpacking depending on return type.
    Prefer returning JSON from Postgres for simplicity.
    Example SQL in Supabase:
        CREATE OR REPLACE FUNCTION get_specific_resident_profile(p_user_id int)
        RETURNS jsonb AS $$
        SELECT to_jsonb(q) FROM (
           -- your joined/select result here
        ) q;
        $$ LANGUAGE sql STABLE;
    """
    with connection.cursor() as cur:
        cur.execute("SELECT get_specific_resident_profile(%s);", [user_id])
        row = cur.fetchone()
    return row[0] if row else None

def get_resident_profile(user_id: int, *, force_refresh: bool = False):
    cache_key = f"profile:resident:{user_id}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    prof = _db_get_resident_profile(user_id)
    # Cache even if None for a short time to avoid hammering DB on missing users
    cache.set(cache_key, prof, PROFILE_TTL)
    return prof

def invalidate_resident_profile(user_id: int):
    cache.delete(f"profile:resident:{user_id}")
