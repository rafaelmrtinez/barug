# staff_admin/context_processors.py
from django.db import connection

def _count_sql(sql: str, params: tuple = ()) -> int:
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row[0] if row and row[0] is not None else 0)
    except Exception:
        return 0

def _staff_account_requests_count() -> int:
    """
    Count staff account requests with status "WAITING FOR ADMIN'S APPROVAL"
    """
    sql = """
        SELECT COUNT(*) AS pending_staff_acc_requests
        FROM (
            SELECT DISTINCT ON (sar.staff_acc_req_id)
                   sar.staff_acc_req_id,
                   COALESCE(sara.request_status_id, 46) AS current_status_id
            FROM staff_account_req sar
            LEFT JOIN staff_acc_req_approval sara 
              ON sar.staff_acc_req_id = sara.staff_acc_req_id
            ORDER BY
              sar.staff_acc_req_id,
              sara.approval_date DESC NULLS LAST
        ) latest
        WHERE latest.current_status_id = 30
    """
    return _count_sql(sql)

def staff_admin_badge_counts(request):
    """
    Exposes staff admin badge counts to all templates as `staff_admin_badge_counts`.
    Example access:
      {{ staff_admin_badge_counts.staff_account_requests_pending }}
    """
    return {
        "staff_admin_badge_counts": {
            "staff_account_requests_pending": _staff_account_requests_count(),
        }
    }