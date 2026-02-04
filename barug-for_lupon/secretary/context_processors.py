# secretary/context_processors.py
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
    Count staff account requests with status "WAITING FOR BARANGAY CAPTAIN'S APPROVAL" or "WAITING FOR BARANGAY SECRETARY'S APPROVAL"
    """
    sql = """
        SELECT COUNT(*) AS pending_staff_acc_requests
        FROM (
            SELECT DISTINCT ON (sara.staff_acc_req_id)
                   sara.staff_acc_req_id,
                   TRIM(UPPER(rs.request_status_name)) AS status_name
            FROM staff_acc_req_approval sara
            JOIN request_status rs
              ON rs.request_status_id = sara.request_status_id
            ORDER BY
              sara.staff_acc_req_id,
              sara.staff_acc_req_approval_id DESC
        ) latest
        WHERE latest.status_name = 'WAITING FOR BARANGAY CAPTAIN''S APPROVAL'
        OR latest.status_name = 'WAITING FOR BARANGAY SECRETARY''S APPROVAL'
    """
    return _count_sql(sql)

def secretary_badge_counts(request):
    """
    Exposes secretary badge counts to all templates as `secretary_badge_counts`.
    Example access:
      {{ secretary_badge_counts.staff_account_requests_pending }}
    """
    return {
        "secretary_badge_counts": {
            "staff_account_requests_pending": _staff_account_requests_count(),
        }
    }