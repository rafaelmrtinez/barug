# authentication/db.py
import logging
from django.db import connection
logger = logging.getLogger("authentication.views")

def call_staff_login(username: str, password: str):
    """
    Calls your Postgres function staff_login(username, password)
    Expected to return (user_id, user_type, role_name[, display_name?])
    Adjust unpacking to match your exact function.
    """
    sql = "SELECT * FROM staff_login(%s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [username, password])
        row = cur.fetchone()
    logger.debug("[DEBUG] DB FETCHONE staff_login | user=%s has_row=%s", username, bool(row))
    return row
