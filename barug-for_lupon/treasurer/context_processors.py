from authentication.supabase_client import supabase
from treasurer.services.requests_service import list_requests, list_business_requests
from django.db import connection

def queue_counts(request):
    """Provide queue counts for navbar badges"""
    counts = {
        'business_count': 0,
        'resident_count': 0,
        'renewal_count': 0,
        'refund_count': 0,
        'lupon_unpaid_count': 0,
    }
    
    try:
        # Business queue count - FOR_TREASURER_REVIEW only
        TARGET_DOCS = {"BARANGAY BUSINESS CLEARANCE", "CERTIFIED TRUE COPY"}
        raw_rows = list_business_requests(None, ["FOR_TREASURER_REVIEW"], limit=100)
        biz_count = 0
        for r in raw_rows:
            docs = [(d or "").strip() for d in (r.get("doc_types") or [])]
            if any(d in TARGET_DOCS for d in docs):
                biz_count += 1
        counts['business_count'] = biz_count
    except Exception:
        pass
    
    try:
        # Resident queue count - FOR_TREASURER_REVIEW only
        rows = list_requests(None, ["FOR_TREASURER_REVIEW"], limit=50)
        EXCLUDE_DOCS = {"BARANGAY BUSINESS CLEARANCE", "CERTIFIED TRUE COPY"}
        filtered = [r for r in rows if not any(dt in EXCLUDE_DOCS for dt in (r.get("doc_types") or []))]
        counts['resident_count'] = len(filtered)
    except Exception:
        pass
    
    try:
        # Business renewal count (unpaid only)
        ren_res = supabase.table("renewal_request").select("renewal_request_id", count="exact").eq("request_status_id", 8).execute()
        if ren_res.count:
            counts['renewal_count'] = ren_res.count
    except Exception:
        pass
    
    try:
        # Payment refunds count (pending only)
        ref_res = supabase.table("payment_refund").select("payment_refund_id", count="exact").in_("status", ["CREATED", "PENDING", "REQUESTED"]).execute()
        if ref_res.count:
            counts['refund_count'] = ref_res.count
    except Exception:
        pass
    
    try:
        # Lupon unpaid reports count (FOR CASE FILING or ESCALATED TO CASE with UNPAID status)
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM blotter_report br
                JOIN v_report_latest_status vr ON vr.blotter_report_id = br.blotter_report_id
                JOIN payment_status ps ON ps.payment_status_id = br.payment_status_id
                WHERE UPPER(vr.report_status_name) IN ('FOR CASE FILING', 'ESCALATED TO CASE')
                AND UPPER(ps.payment_status_name) = 'UNPAID'
            """)
            result = cur.fetchone()
            if result and result[0]:
                counts['lupon_unpaid_count'] = result[0]
    except Exception:
        pass
    
    return counts
