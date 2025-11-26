# lupon_mem/context_processors.py
from django.db import connection

def lupon_badge_counts(request):
    """
    Expose unpaid counts globally:
    - unpaid_reports_count: blotter_report rows with NULL payment_status_id or status != 'PAID'
    - unpaid_cases_count:  barangay_case rows with NULL payment_status_id or status != 'PAID' (0 if table not present)
    """
    counts = {"unpaid_reports_count": 0, "unpaid_cases_count": 0}

    with connection.cursor() as cur:
        # Unpaid / no payment blotter reports
        cur.execute("""
            SELECT COUNT(*)
              FROM blotter_report br
              LEFT JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
             WHERE br.payment_status_id IS NULL
                OR UPPER(ps.payment_status_name) <> 'PAID'
        """)
        counts["unpaid_reports_count"] = int(cur.fetchone()[0] or 0)

        # Unpaid / no payment barangay cases (if your case table tracks payment)
        try:
            cur.execute("""
                SELECT COUNT(*)
                  FROM barangay_case bc
                  LEFT JOIN payment_status ps ON ps.payment_status_id = bc.payment_status_id
                 WHERE bc.payment_status_id IS NULL
                    OR UPPER(ps.payment_status_name) <> 'PAID'
            """)
            counts["unpaid_cases_count"] = int(cur.fetchone()[0] or 0)
        except Exception:
            # If you don't have a payment_status on cases yet, just show 0
            counts["unpaid_cases_count"] = 0
    
    # Add lupon schedule from session
    auth = request.session.get("auth", {})
    counts["lupon_sched"] = auth.get("lupon_sched", [])

    return counts
