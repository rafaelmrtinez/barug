# lupon_mem/services/case_state.py
from django.db import connection

def _exec(fn_sql: str, params: list | tuple):
    with connection.cursor() as cur:
        cur.execute(fn_sql, params)

def close_case(blotter_case_id: int, staff_id: int, note: str | None = None) -> None:
    """
    Calls the DB helper close_blotter_case(p_case_id, p_by_staff_id, p_close_note)
    """
    _exec("SELECT close_blotter_case(%s, %s, %s)", [blotter_case_id, staff_id, note])

def reopen_case(blotter_case_id: int, staff_id: int, reason: str | None = None) -> None:
    """
    Calls the DB helper reopen_blotter_case(p_case_id, p_by_staff_id, p_reason)
    """
    _exec("SELECT reopen_blotter_case(%s, %s, %s)", [blotter_case_id, staff_id, reason])
