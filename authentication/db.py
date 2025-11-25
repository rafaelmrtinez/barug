# authentication/db.py
import logging
from django.db import connection
logger = logging.getLogger("authentication.views")

def call_staff_login(username: str, password: str, ip_address: str = None):
    """
    Calls your Postgres function staff_login(username, password, ip_address)
    Expected to return (user_id, person_id, user_type, role_name, first_name, middle_name, last_name, account_status_name)
    """
    sql = "SELECT * FROM staff_login2(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [username, password, ip_address])
        row = cur.fetchone()
    logger.debug("[DEBUG] DB FETCHONE staff_login | user=%s has_row=%s", username, bool(row))
    return row

def call_change_staff_password(staff_id: int, new_password: str, retyped_password: str):
    """
    Calls the change_staff_password function to securely change password
    Returns True on success, raises exception on failure
    """
    sql = "SELECT change_staff_password(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [staff_id, new_password, retyped_password])
        result = cur.fetchone()
    return result[0] if result else False

def call_staff_request_password_reset(email: str, request_ip: str = None, ttl_minutes: int = 60):
    """
    Calls the password reset request function
    Returns list of (staff_id, username, email, reset_token) tuples
    """
    sql = "SELECT * FROM call_staff_request_password_reset(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [email, request_ip, ttl_minutes])
        rows = cur.fetchall()
    return rows

def call_staff_reset_password_with_token(token: str, new_password: str, retyped_password: str):
    """
    Calls the password reset with token function
    Returns True on success, raises exception on failure
    """
    sql = "SELECT call_staff_reset_password_with_token(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [token, new_password, retyped_password])
        result = cur.fetchone()
    return result[0] if result else False

def call_staff_check_password_reset_token(token: str):
    """
    Checks if a password reset token is valid (exists, not expired, not used)
    Returns True if valid, False otherwise
    """
    sql = "SELECT call_staff_check_password_reset_token(%s);"
    with connection.cursor() as cur:
        cur.execute(sql, [token])
        result = cur.fetchone()
    return result[0] if result else False

def call_staff_logout(login_log_id: int, staff_id: int, ip_address: str = None):
    """
    Calls the staff_logout2 function to properly log out a user session
    Returns the updated login_log record
    """
    sql = "SELECT * FROM staff_logout2(%s, %s, %s);"
    with connection.cursor() as cur:
        cur.execute(sql, [login_log_id, staff_id, ip_address])
        row = cur.fetchone()
    return row

def get_staff_common_logs_with_names(staff_id: int):
    """
    Gets operational logs for a staff member with formatted names
    Returns list of dictionaries with log details
    """
    sql = "SELECT * FROM get_staff_common_logs_with_names(%s);"
    with connection.cursor() as cur:
        cur.execute(sql, [staff_id])
        columns = [col[0] for col in cur.description]
        rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]
