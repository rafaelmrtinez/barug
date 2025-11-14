# authentication/db.py
import logging
from django.db import connection
logger = logging.getLogger("authentication.views")

def call_staff_login(username: str, password: str, ip_address: str = None):
    """
    Calls your Postgres function staff_login(username, password, ip_address)
    Expected to return (user_id, person_id, user_type, role_name, first_name, middle_name, last_name, account_status_name)
    """
    sql = "SELECT * FROM staff_login(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [username, password, ip_address])
        row = cur.fetchone()
    logger.debug("[DEBUG] DB FETCHONE staff_login | user=%s has_row=%s", username, bool(row))
    return row
