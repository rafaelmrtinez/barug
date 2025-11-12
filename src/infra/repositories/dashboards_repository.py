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
            AND dr.created_at::date = CURRENT_DATE;
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
            WHERE b.created_at >= date_trunc('week', now())
            AND b.created_at < date_trunc('week', now()) + INTERVAL '7 days';
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
            SELECT COUNT(*) AS kpi_sub_total_residents_this_month
            FROM public.person p
            JOIN public.residential_status r
            ON p.residential_status_id = r.residential_status_id
            WHERE UPPER(r.residential_status_name) = 'RESIDENT'
            AND p.date_added >= date_trunc('month', now())
            AND p.date_added < date_trunc('month', now()) + INTERVAL '1 month';
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

class TreasurerDashboardRepository:
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_kpi_pending_payments(self) -> int:
        query = """
            SELECT
            (SELECT COUNT(*)
            FROM public.doc_request_hdr dr
            JOIN public.request_status rs ON dr.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW') AS doc_request_count,

            (SELECT COUNT(*)
            FROM public.renewal_request rr
            JOIN public.request_status rs ON rr.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW') AS renewal_request_count,

            (SELECT COUNT(*)
            FROM public.closure_payment_request cp
            JOIN public.request_status rs ON cp.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW') AS closure_request_count,

            (SELECT COUNT(*)
            FROM public.blotter_case_payment bp
            JOIN public.payment_status ps ON bp.payment_status_id = ps.payment_status_id
            WHERE ps.payment_status_name = 'UNPAID') AS unpaid_blotter_payment_count,

            -- Sum of all
            (
            (SELECT COUNT(*) FROM public.doc_request_hdr dr
            JOIN public.request_status rs ON dr.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW')
            +
            (SELECT COUNT(*) FROM public.renewal_request rr
            JOIN public.request_status rs ON rr.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW')
            +
            (SELECT COUNT(*) FROM public.closure_payment_request cp
            JOIN public.request_status rs ON cp.request_status_id = rs.request_status_id
            WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW')
            +
            (SELECT COUNT(*) FROM public.blotter_case_payment bp
            JOIN public.payment_status ps ON bp.payment_status_id = ps.payment_status_id
            WHERE ps.payment_status_name = 'UNPAID')
            ) AS total_count;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('pending_payments') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI pending payments: {str(e)}",
                code="KPI_PENDING_PAYMENTS"
            )

    def fetch_kpi_sub_pending_payments(self) -> int:
        query = """
            WITH
                doc_today AS (
                    SELECT COUNT(*) AS cnt
                    FROM public.doc_request_hdr dr
                    JOIN public.request_status rs ON dr.request_status_id = rs.request_status_id
                    WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW'
                    AND dr.created_at::date = current_date
                ),
                renewal_today AS (
                    SELECT COUNT(*) AS cnt
                    FROM public.renewal_request rr
                    JOIN public.request_status rs ON rr.request_status_id = rs.request_status_id
                    WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW'
                    AND rr.created_at::date = current_date
                ),
                closure_today AS (
                    SELECT COUNT(*) AS cnt
                    FROM public.closure_payment_request cp
                    JOIN public.request_status rs ON cp.request_status_id = rs.request_status_id
                    WHERE rs.request_status_name = 'FOR_TREASURER_REVIEW'
                    AND cp.created_at::date = current_date
                ),
                blotter_today AS (
                    SELECT COUNT(*) AS cnt
                    FROM public.blotter_case_payment bp
                    JOIN public.payment_status ps ON bp.payment_status_id = ps.payment_status_id
                    WHERE ps.payment_status_name = 'UNPAID'
                    AND bp.date_of_payment::date = current_date
                )
            SELECT
                (SELECT cnt FROM doc_today) AS doc_request_today_count,
                (SELECT cnt FROM renewal_today) AS renewal_request_today_count,
                (SELECT cnt FROM closure_today) AS closure_request_today_count,
                (SELECT cnt FROM blotter_today) AS unpaid_blotter_payment_today_count,
                (
                    (SELECT cnt FROM doc_today)
                + (SELECT cnt FROM renewal_today)
                + (SELECT cnt FROM closure_today)
                + (SELECT cnt FROM blotter_today)
                ) AS total_today_count;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('sub_pending_payments') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI sub pending payments: {str(e)}",
                code="KPI_SUB_PENDING_PAYMENTS"
            )

    def fetch_kpi_official_receipts_issued_this_week(self) -> int:
        query = """
            SELECT COUNT(*) AS or_count_week
            FROM public.official_receipt
            WHERE issued_at >= date_trunc('week', now())
            AND issued_at < date_trunc('week', now()) + INTERVAL '7 days';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('or_issued_this_week') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI official receipts issued this week: {str(e)}",
                code="KPI_OR_ISSUED_THIS_WEEK"
            )
    
    def fetch_kpi_sub_official_receipts_issued_this_week(self) -> int:
        query = """
            SELECT COUNT(*) AS or_count_today
            FROM public.official_receipt
            WHERE issued_at::date = current_date;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('or_issued_today') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI official receipts issued today: {str(e)}",
                code="KPI_SUB_OR_ISSUED_TODAY"
            )

    def fetch_kpi_collections_this_week(self) -> int:
        query = """
            SELECT SUM(amount_paid) AS total_amount_collected_week
            FROM public.official_receipt
            WHERE issued_at >= date_trunc('week', now())
            AND issued_at < date_trunc('week', now()) + INTERVAL '7 days';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return float(row.get('collections_this_week') or 0)
            return float(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI collections this week: {str(e)}",
                code="KPI_COLLECTIONS_THIS_WEEK"
            )

    def fetch_kpi_sub_collections_this_week(self) -> int:
        query = """
            SELECT SUM(amount_paid) AS total_amount_collected_today
            FROM public.official_receipt
            WHERE issued_at::date = current_date;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return float(row.get('collections_this_month') or 0)
            return float(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI collections this month: {str(e)}",
                code="KPI_COLLECTIONS_THIS_WEEK"
            )

    def fetch_kpi_collections_this_year(self) -> int:
        query = """
            SELECT SUM(amount_paid) AS total_amount_collected_year
            FROM public.official_receipt
            WHERE issued_at >= date_trunc('year', now())
            AND issued_at < date_trunc('year', now()) + INTERVAL '1 year';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return float(row.get('collections_this_year') or 0)
            return float(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI collections this year: {str(e)}",
                code="KPI_COLLECTIONS_THIS_YEAR"
            )

    def fetch_kpi_sub_collections_this_year(self) -> int:
        query = """
            SELECT SUM(amount_paid) AS total_amount_collected_month
            FROM public.official_receipt
            WHERE issued_at >= date_trunc('month', now())
            AND issued_at < date_trunc('month', now()) + INTERVAL '1 month';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return float(row.get('collections_this_year') or 0)
            return float(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI collections this year: {str(e)}",
                code="KPI_SUB_COLLECTIONS_THIS_YEAR"
            )

    def fetch_collections_trend_last_7_days(self) -> dict:
        """
        Returns: {"labels": ["Mon","Tue",...], "data": [123.45, ...]}
        Uses Asia/Manila timezone and returns SUM(amount_paid) per day for the last 7 calendar days (oldest first).
        """
        query = """
            SELECT
              to_char(d.day, 'Dy') AS label,
              COALESCE(t.total_amount, 0) AS total_amount_collected
            FROM (
              SELECT (date_trunc('day', now() AT TIME ZONE 'Asia/Manila')::date - (s.i * INTERVAL '1 day'))::date AS day
              FROM generate_series(6, 0, -1) AS s(i)
            ) d
            LEFT JOIN (
              SELECT
                (issued_at AT TIME ZONE 'Asia/Manila')::date AS day,
                SUM(amount_paid) AS total_amount
              FROM public.official_receipt
              WHERE issued_at >= (date_trunc('day', now() AT TIME ZONE 'Asia/Manila')::date - INTERVAL '6 days')
                AND issued_at <  (date_trunc('day', now() AT TIME ZONE 'Asia/Manila')::date + INTERVAL '1 day')
              GROUP BY (issued_at AT TIME ZONE 'Asia/Manila')::date
            ) t ON t.day = d.day
            ORDER BY d.day;
        """
        try:
            rows = self._ctx.execute_query(query)
            # normalize to {"labels": [...], "data": [...]}
            if not rows:
                return {"labels": [], "data": []}

            labels = []
            data = []
            for r in rows:
                if isinstance(r, dict):
                    labels.append(r.get("label"))
                    # ensure numeric
                    val = r.get("total_amount_collected")
                else:
                    # tuple-like (label, value)
                    labels.append(r[0])
                    val = r[1]
                # safe cast to float
                try:
                    data.append(float(val or 0))
                except Exception:
                    data.append(0.0)

            return {"labels": labels, "data": data}
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch collection trend : {str(e)}",
                code="COLLECTIONS_TREND"
            )

    def fetch_collections_per_month(self) -> dict:
        """
        Returns: {"labels": ["Jan","Feb",...], "data": [1234.56, ...]}
        Sum of collections per month for the current year (Jan..Dec).
        """
        query = """
            SELECT
              to_char(m.first_day, 'Mon') AS month_label,
              COALESCE(t.total_amount, 0) AS total_amount_collected
            FROM (
              SELECT (date_trunc('year', now()) + (n * INTERVAL '1 month'))::date AS first_day
              FROM generate_series(0, 11) AS gs(n)
            ) m
            LEFT JOIN (
              SELECT
                date_trunc('month', issued_at AT TIME ZONE 'Asia/Manila')::date AS first_day,
                SUM(amount_paid) AS total_amount
              FROM public.official_receipt
              WHERE issued_at >= date_trunc('year', now())
                AND issued_at <  date_trunc('year', now()) + INTERVAL '1 year'
              GROUP BY date_trunc('month', issued_at AT TIME ZONE 'Asia/Manila')::date
            ) t ON t.first_day = m.first_day
            ORDER BY m.first_day;
        """
        try:
            rows = self._ctx.execute_query(query)
            if not rows:
                return {"labels": [], "data": []}

            labels = []
            data = []
            for r in rows:
                if isinstance(r, dict):
                    labels.append(r.get("month_label"))
                    val = r.get("total_amount_collected")
                else:
                    labels.append(r[0])
                    val = r[1]
                try:
                    data.append(float(val or 0))
                except Exception:
                    data.append(0.0)

            return {"labels": labels, "data": data}
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch collections per month: {str(e)}",
                code="COLLECTIONS_PER_MONTH"
            )

class CaptainDashboardRepository:
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        self._clerk_repo = ClerkDashboardRepository(ctx)
        self._treasurer_repo = TreasurerDashboardRepository(ctx)

    def fetch_kpi_ongoing_cases(self) -> int:
        query = """
            SELECT COUNT(*) AS ongoing_cases
            FROM public.blotter_case bc
            JOIN public.settlement_status ss
            ON bc.settlement_status_id = ss.settlement_status_id
            WHERE ss.settlement_status_name = 'ONGOING';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('ongoing_cases') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI ongoing cases: {str(e)}",
                code="KPI_ONGOING_CASES"
            )
        
    def fetch_kpi_sub_ongoing_cases(self) -> int:
        query = """
            SELECT COUNT(*) AS open_cases
            FROM public.blotter_case bc
            JOIN public.case_state cs
            ON bc.case_state_id = cs.case_state_id
            WHERE cs.case_state_name = 'OPEN';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('ongoing_cases_sub') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI ongoing cases sub: {str(e)}",
                code="KPI_SUB_ONGOING_CASES"
            )

    # Residents KPIs (from Clerk repo)
    def fetch_kpi_total_residents(self) -> int:
        return self._clerk_repo.fetch_kpi_total_residents()

    def fetch_kpi_sub_total_residents(self) -> int:
        return self._clerk_repo.fetch_kpi_sub_total_residents()

    # Collections KPIs (from Treasurer repo)
    def fetch_kpi_collections_this_week(self) -> float:
        return self._treasurer_repo.fetch_kpi_collections_this_week()

    def fetch_kpi_sub_collections_this_week(self) -> float:
        return self._treasurer_repo.fetch_kpi_sub_collections_this_week()

    def fetch_kpi_collections_this_year(self) -> float:
        return self._treasurer_repo.fetch_kpi_collections_this_year()

    def fetch_kpi_sub_collections_this_year(self) -> float:
        return self._treasurer_repo.fetch_kpi_sub_collections_this_year()

    def fetch_case_nature_counts(self) -> dict:
        query = """
            SELECT 
                cn.case_name,
                COUNT(bc.blotter_case_id) AS case_count
            FROM public.case_nature cn
            LEFT JOIN public.blotter_case bc
                ON bc.case_nature_id = cn.case_nature_id
            GROUP BY cn.case_name
            ORDER BY case_count DESC;
        """
        try:
            rows = self._ctx.execute_query(query)
            if not rows:
                return {}
            result = {}
            for r in rows:
                if isinstance(r, dict):
                    nature = r.get("case_name")
                    cnt = int(r.get("case_count") or 0)
                else:
                    nature = r[0]
                    cnt = int(r[1] or 0)
                result[nature] = cnt
            return result
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch case nature counts: {str(e)}",
                code="CASE_NATURE_COUNTS"
            )

    # Collections per month chart (from Treasurer repo)
    def fetch_collections_per_month(self) -> dict:
        return self._treasurer_repo.fetch_collections_per_month()

class SecretaryDashboardRepository:
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        self._captain_repo = CaptainDashboardRepository(ctx)
        self._clerk_repo = ClerkDashboardRepository(ctx)

    def fetch_kpi_ongoing_cases(self) -> int:
        return self._captain_repo.fetch_kpi_ongoing_cases()
    
    def fetch_kpi_sub_ongoing_cases(self) -> int:
        return self._captain_repo.fetch_kpi_sub_ongoing_cases()
    
    def fetch_kpi_active_biz(self) -> int:
        return self._clerk_repo.fetch_kpi_active_biz()
    
    def fetch_kpi_sub_active_biz(self) -> int:
        return self._clerk_repo.fetch_kpi_sub_active_biz()

    def fetch_kpi_demographics(self) -> int:
        query = """
            SELECT COUNT(*) AS active_household_count
            FROM public.household_info
            WHERE COALESCE(is_active, FALSE) = TRUE;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi_demographics') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI demographics: {str(e)}",
                code="KPI_DEMOGRAPHICS"
            )

    def fetch_kpi_sub_demographics(self) -> int:
        query = """
            SELECT COUNT(*) AS active_family_count
            FROM public.family_unit
            WHERE COALESCE(is_active, FALSE) = TRUE;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('kpi__sub_demographics') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI SUB demographics: {str(e)}",
                code="KPI__SUB_DEMOGRAPHICS"
            )
    
    def fetch_kpi_total_residents(self) -> int:
        return self._clerk_repo.fetch_kpi_total_residents()
    
    def fetch_kpi_sub_total_residents(self) -> int:
        return self._clerk_repo.fetch_kpi_sub_total_residents()
    
    def fetch_case_nature_counts(self) -> dict:
        return self._captain_repo.fetch_case_nature_counts()
    
    def fetch_biz_status_counts(self) -> dict:
        return self._clerk_repo.fetch_biz_status_counts()

class LuponMemDashboardRepository:
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        self._captain_repo = CaptainDashboardRepository(ctx)

    def fetch_kpi_ongoing_cases(self) -> int:
        return self._captain_repo.fetch_kpi_ongoing_cases()
    
    def fetch_kpi_sub_ongoing_cases(self) -> int:
        return self._captain_repo.fetch_kpi_sub_ongoing_cases()
    
    def fetch_kpi_total_cases_settled(self) -> int:
        query = """
            SELECT COUNT(*) AS total_cases_settled
            FROM public.blotter_case bc
            JOIN public.settlement_status ss
            ON bc.settlement_status_id = ss.settlement_status_id
            WHERE ss.settlement_status_name = 'SETTLED';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('total_cases_settled') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total cases settled: {str(e)}",
                code="KPI_TOTAL_CASES_SETTLED"
            )

    def fetch_kpi_sub_total_cases_settled(self) -> int:
        query = """

        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('total_cases_settled_sub') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total cases settled sub: {str(e)}",
                code="KPI_TOTAL_CASES_SETTLED_SUB"
            )

    def fetch_kpi_total_cases_unsettled(self) -> int:
        query = """
            SELECT COUNT(*) AS total_cases_unsettled
            FROM public.blotter_case bc
            JOIN public.settlement_status ss
            ON bc.settlement_status_id = ss.settlement_status_id
            WHERE ss.settlement_status_name = 'NOT SETTLED';
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('total_cases_unsettled') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total cases unsettled: {str(e)}",
                code="KPI_TOTAL_CASES_UNSETTLED"
            )

    def fetch_kpi_sub_total_cases_unsettled(self) -> int:
        query = """
    
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('total_cases_unsettledd_sub') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total cases unsettled sub: {str(e)}",
                code="KPI_TOTAL_CASES_UNSETTLED_SUB"
            )

    def fetch_kpi_settlement_rate(self) -> int:
        query = """
            WITH status_counts AS (
                SELECT
                    SUM(CASE 
                            WHEN ss.settlement_status_name = 'SETTLED' 
                                AND cs.case_state_name = 'CLOSED'
                            THEN 1 ELSE 0 END) AS settled_closed_count,
                    SUM(CASE 
                            WHEN ss.settlement_status_name = 'NOT SETTLED' 
                                AND cs.case_state_name = 'CLOSED'
                            THEN 1 ELSE 0 END) AS not_settled_closed_count
                FROM public.blotter_case bc
                LEFT JOIN public.settlement_status ss
                    ON bc.settlement_status_id = ss.settlement_status_id
                LEFT JOIN public.case_state cs
                    ON bc.case_state_id = cs.case_state_id
            )
            SELECT
                CASE 
                    WHEN not_settled_closed_count = 0 THEN NULL
                    ELSE ROUND(100.0 * settled_closed_count / not_settled_closed_count, 2)
                END AS settlement_percentage
            FROM status_counts;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            row = result[0]
            if isinstance(row, dict):
                return int(row.get('settlement_rate') or 0)
            return int(row[0] or 0)
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch settlement_rate: {str(e)}",
                code="SETTLEMENT_RATE"
            )

    def fetch_case_nature_counts(self) -> dict:
        return self._captain_repo.fetch_case_nature_counts()

    def fetch_settlement_status_counts(self) -> int:
        query = """
            SELECT
            ss.settlement_status_name AS settlement_status,
            COUNT(bc.blotter_case_id) AS case_count
            FROM public.settlement_status ss
            LEFT JOIN public.blotter_case bc
            ON bc.settlement_status_id = ss.settlement_status_id
            GROUP BY ss.settlement_status_id, ss.settlement_status_name
            ORDER BY case_count DESC;
        """
        try:
            result = self._ctx.execute_query(query)
            if not result:
                return 0
            normalized = []
            for row in result:
                if isinstance(row, dict):
                    normalized.append({
                        "settlement_status": row.get("settlement_status"),
                        "case_count": int(row.get("case_count") or 0)
                    })
                else:
                    # tuple-like
                    normalized.append({
                        "settlement_status": row[0],
                        "case_count": int(row[1] or 0)
                    })
            return normalized
        except Exception as e:
            raise QueryExecutionException(
                f"Error executing query to fetch KPI total cases open: {str(e)}",
                code="KPI_TOTAL_CASES_OPEN"
            )

