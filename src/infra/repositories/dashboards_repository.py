from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException

class ClerkDashboardRepository:
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_kpi_doc_req(self) -> int:
        query = """
            SELECT COUNT(*) AS doc_requests_for_clerk_review
            FROM public.doc_request_hdr dr
            JOIN public.request_status rs
            ON dr.request_status_id = rs.request_status_id
            WHERE UPPER(rs.request_status_name) = 'FOR CLERK REVIEW';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            # defensive: handle different shapes (dict row or tuple)
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_doc_req') or 0)
            # if it's a tuple/cursor-like
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI document requests today: {str(e)}",
                code="KPI_DOC_REQ"
            )
    
    def fetch_kpi_sub_doc_req(self) -> int:
        query = """
            SELECT COUNT(*) AS doc_requests_for_clerk_review_today
            FROM public.doc_request_hdr dr
            JOIN public.request_status rs
            ON dr.request_status_id = rs.request_status_id
            WHERE UPPER(rs.request_status_name) = 'FOR CLERK REVIEW'
            AND dr.created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Manila')
            AND dr.created_at < (date_trunc('day', now() AT TIME ZONE 'Asia/Manila') + INTERVAL '1 day');
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            # defensive: handle different shapes (dict row or tuple)
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_sub_doc_req') or 0)
            # if it's a tuple/cursor-like
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI document requests today: {str(e)}",
                code="KPI_SUB_DOC_REQ"
            )

    def fetch_kpi_pending_verifications(self) -> int:
        query = """
            SELECT COUNT(*) as kpi_pending_verifications
            FROM get_id_validation_requests();
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_pending_verifications') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI pending verifications: {str(e)}",
                code="KPI_PENDING_VERIF"
            )
        
    def fetch_kpi_sub_pending_verifications(self) -> int:
        query = """
            SELECT COUNT(*) AS pending_today
            FROM get_id_validation_requests()
            WHERE date_requested::date = CURRENT_DATE;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_sub_pending_verifications') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI pending verifications: {str(e)}",
                code="KPI_SUB_PENDING_VERIF"
            )
    
    def fetch_kpi_active_biz(self) -> int:
        query = """
            SELECT COUNT(*) AS kpi_active_biz
            FROM public.business b
            JOIN public.business_status s
              ON b.business_status_id = s.business_status_id
            WHERE UPPER(s.business_status_name) = 'ACTIVE';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_active_biz') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI active businesses: {str(e)}",
                code="KPI_ACTIVE_BIZ"
            )
        
    def fetch_kpi_sub_active_biz(self) -> int:
        query = """
            SELECT COUNT(*) 
            FROM business b
            WHERE b.created_at >= date_trunc('week', CURRENT_DATE - INTERVAL '1 week')
            AND b.created_at < date_trunc('week', CURRENT_DATE);
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_sub_active_biz') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI active businesses: {str(e)}",
                code="KPI_SUB_ACTIVE_BIZ"
            )
        
    def fetch_kpi_total_residents(self) -> int:
        query = """
            SELECT COUNT(*) AS kpi_total_residents
            FROM public.person p
            JOIN public.residential_status r
              ON p.residential_status_id = r.residential_status_id
            WHERE UPPER(r.residential_status_name) = 'RESIDENT';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_total_residents') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total residents: {str(e)}",
                code="KPI_TOTAL_RESIDENTS"
            )
        
    def fetch_kpi_sub_total_residents(self) -> int:
        query = """
            SELECT COUNT(*) AS kpi_total_residents
            FROM public.person p
            JOIN public.residential_status r
              ON p.residential_status_id = r.residential_status_id
            WHERE UPPER(r.residential_status_name) = 'RESIDENT'
			AND p.date_added >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month')
            AND p.date_added < date_trunc('month', CURRENT_DATE);
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_sub_total_residents') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total residents: {str(e)}",
                code="KPI_SUB_TOTAL_RESIDENTS"
            )

    def fetch_biz_status_counts(self) -> dict:
        query = """
            WITH wanted(status_name) AS (
            VALUES ('ACTIVE'), ('PENDING'), ('CLOSED'), ('EXPIRED')
            ),
            counts AS (
            SELECT UPPER(bs.business_status_name) AS status_name, COUNT(*) AS cnt
            FROM public.business b
            JOIN public.business_status bs
                ON b.business_status_id = bs.business_status_id
            WHERE UPPER(bs.business_status_name) IN ('ACTIVE','PENDING','CLOSED','EXPIRED')
            GROUP BY UPPER(bs.business_status_name)
            )
            SELECT w.status_name AS status,
                COALESCE(c.cnt, 0) AS cnt
            FROM wanted w
            LEFT JOIN counts c ON c.status_name = w.status_name
            ORDER BY w.status_name;
        """
        try:
            rows = self._ctx.execute_query(query)
            if not rows:
                return {"ACTIVE":0, "PENDING":0, "CLOSED":0, "EXPIRED":0}
            # rows may be list of dicts or tuples
            result = {}
            for r in rows:
                if isinstance(r, dict):
                    status = r.get("status")
                    cnt = int(r.get("cnt") or 0)
                else:
                    status = r[0]
                    cnt = int(r[1] or 0)
                result[status] = cnt
            # ensure keys exist
            for k in ("ACTIVE","PENDING","CLOSED","EXPIRED"):
                result.setdefault(k, 0)
            return result
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch business status counts: {str(e)}",
                code="BIZ_STATUS_COUNTS"
            )

    def fetch_requests_trend_last_7_days(self) -> dict:
        """
        Returns: {"labels": ["Mon","Tue",...], "data": [12,5,...]}
        Uses Asia/Manila timezone and returns counts for the last 7 calendar days
        (oldest first).
        """
        query = """
            SELECT
            to_char(d.day::date, 'Dy') AS label,
            COALESCE(counts.cnt, 0) AS cnt
            FROM (
            SELECT (date_trunc('day', now() AT TIME ZONE 'Asia/Manila')::date - (i || ' days')::interval)::date AS day
            FROM generate_series(6,0,-1) AS s(i)
            ) d
            LEFT JOIN (
            SELECT (created_at AT TIME ZONE 'Asia/Manila')::date AS day,
                    COUNT(*) AS cnt
            FROM public.doc_request_hdr
            GROUP BY (created_at AT TIME ZONE 'Asia/Manila')::date
            ) counts
            ON counts.day = d.day
            ORDER BY d.day;
        """
        try:
            rows = self._ctx.execute_query(query)
            if not rows:
                return {"labels": [], "data": []}
            labels = []
            data = []
            for r in rows:
                if isinstance(r, dict):
                    labels.append(r.get("label"))
                    data.append(int(r.get("cnt") or 0))
                else:
                    labels.append(r[0])
                    data.append(int(r[1] or 0))
            return {"labels": labels, "data": data}
        except Exception as e:
            raise QueryExecutionException(f"Error fetching requests trend: {e}", code="REQS_TREND")
