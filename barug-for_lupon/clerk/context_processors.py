# clerk/context_processors.py
from __future__ import annotations
from collections import defaultdict
from typing import Dict
from django.db import connection

def _count_sql(sql: str, params: tuple = ()) -> int:
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return int(row[0] if row and row[0] is not None else 0)
    except Exception:
        return 0

def _doc_request_counts() -> Dict[str, int]:
    """
    Reads public.doc_request_hdr joined to public.request_status and
    summarizes into canonical buckets used by the navbar.
    Works even if your request_status table contains duplicate spellings.
    """
    by_name = defaultdict(int)

    try:
        with connection.cursor() as cur:
            cur.execute("""
                SELECT rs.request_status_name, COUNT(*)::int
                FROM public.doc_request_hdr d
                JOIN public.request_status rs
                  ON rs.request_status_id = d.request_status_id
                GROUP BY rs.request_status_name
            """)
            for status_name, n in cur.fetchall():
                by_name[(status_name or "").upper().strip()] += int(n)
    except Exception:
        # If something goes wrong, return empty counts (UI will just show 0)
        by_name = defaultdict(int)

    # Map many names → one bucket
    def sum_of(*labels: str) -> int:
        return sum(by_name[l.upper()] for l in labels)

    return {
        "for_clerk_review":       sum_of("FOR CLERK REVIEW", "FOR_CLERK_REVIEW"),
        "for_treasurer_review":   sum_of("FOR_TREASURER_REVIEW"),
        "payment_initiated":      sum_of("PAYMENT_INITIATED"),
        "paid":                   sum_of("PAID"),
        "for_printing":           sum_of("FOR_PRINTING"),
        "released":               sum_of("RELEASED", "ISSUED"),
        "ready_for_pickup":       sum_of("READY_FOR_PICKUP", "READY FOR PICKUP"),
        "declined":               sum_of("DECLINED", "DECLINE", "REJECTED"),
        "cancelled":              sum_of("CANCELLED"),
        # Add more buckets here if you introduce new statuses
    }

def _idv_pending_count() -> int:
    """
    Identity Verification badge. Tries the common schema you use:
    verify_person_acc_req → verification_record → verification_status.
    If the tables/columns aren’t present, it safely returns 0.
    """
    # PENDING / PENDING VERIFICATION both treated as pending
    sql = """
        SELECT COUNT(*)::int
        FROM public.verify_person_acc_req v
        JOIN public.verification_record vr
          ON vr.verification_record_id = v.verification_record_id
        JOIN public.verification_status vs
          ON vs.verification_status_id = vr.verification_status_id
        WHERE UPPER(vs.verification_status_name) IN ('PENDING', 'PENDING VERIFICATION')
    """
    return _count_sql(sql)

def app_badge_counts(request):
    """
    Exposes counts to all templates as `app_badge_counts`.
    Example access:
      {{ app_badge_counts.doc_requests.for_clerk_review }}
      {{ app_badge_counts.idv_pending }}
    """
    doc_counts = _doc_request_counts()
    total_docs = sum(doc_counts.values())

    return {
        "app_badge_counts": {
            "doc_requests": doc_counts,
            "doc_requests_total": total_docs,
            "idv_pending": _idv_pending_count(),
        }
    }
