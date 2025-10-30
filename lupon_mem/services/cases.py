# lupon_mem/services/cases.py
from __future__ import annotations
from django.db import connection, transaction

class CaseServiceError(Exception):
    pass


def _get_staff_id(request) -> int:
    """
    Resolve the current staff_id from session or mapping to the auth user.
    Falls back to staff.user_id if you keep that relation.
    """
    sid = request.session.get("staff_id")
    if sid:
        return int(sid)

    user_id = getattr(request.user, "id", None)
    if not user_id:
        raise CaseServiceError("Cannot determine current staff user.")

    with connection.cursor() as cur:
        # Adjust this query if your schema differs
        cur.execute(
            """
            SELECT s.staff_id
            FROM staff s
            WHERE s.user_id = %s
              AND (s.is_active IS DISTINCT FROM FALSE)
            ORDER BY s.staff_id
            LIMIT 1
            """,
            [user_id],
        )
        row = cur.fetchone()

    if not row:
        raise CaseServiceError("Cannot determine current staff user.")

    return int(row[0])


@transaction.atomic
def close_case(request, case_id: int, note: str | None = None) -> None:
    """
    Calls close_blotter_case(p_blotter_case_id, p_by_staff_id, p_close_note)
    """
    staff_id = _get_staff_id(request)
    with connection.cursor() as cur:
        cur.execute("SELECT close_blotter_case(%s,%s,%s)", [case_id, staff_id, note])


@transaction.atomic
def reopen_case(request, case_id: int, reason: str | None = None) -> None:
    """
    Calls reopen_blotter_case(p_blotter_case_id, p_by_staff_id, p_reason)
    """
    staff_id = _get_staff_id(request)
    with connection.cursor() as cur:
        cur.execute("SELECT reopen_blotter_case(%s,%s,%s)", [case_id, staff_id, reason])
