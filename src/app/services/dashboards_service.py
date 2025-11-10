class ClerkDashboardService:
    def __init__(
        self,
        dashboard_repo
    ):
        self.repo = dashboard_repo

    def get_dashboard_content(self) -> dict:
        kpi_doc_req = self.repo.fetch_kpi_doc_req()
        kpi_sub_doc_req = self.repo.fetch_kpi_sub_doc_req()
        kpi_pending_verifications = self.repo.fetch_kpi_pending_verifications()
        kpi_sub_pending_verifications = self.repo.fetch_kpi_sub_pending_verifications()
        kpi_active_biz = self.repo.fetch_kpi_active_biz()
        kpi_sub_active_biz = self.repo.fetch_kpi_sub_active_biz()
        kpi_total_residents = self.repo.fetch_kpi_total_residents()
        kpi_sub_total_resident = self.repo.fetch_kpi_sub_total_residents()

        requests_trend = self.repo.fetch_requests_trend_last_7_days()

        biz_status_counts = self.repo.fetch_biz_status_counts() 
        status_labels = ["ACTIVE", "PENDING", "CLOSED", "EXPIRED"]
        status_data = [biz_status_counts.get(s, 0) for s in status_labels]

        kpis = {
            "doc_requests": kpi_doc_req,
            "doc_requests_delta": kpi_sub_doc_req,              
            "pending_verifications": kpi_pending_verifications,
            "verif_delta": kpi_sub_pending_verifications,       
            "active_businesses": kpi_active_biz,
            "new_businesses_week": kpi_sub_active_biz,
            "residents_total": kpi_total_residents,
            "new_residents_month": kpi_sub_total_resident,
        }

        dashboard_json = {
            "requestsTrend": {
                "labels": requests_trend.get("labels", []),
                "data": requests_trend.get("data", [])
            },
            "statusBreakdown": {
                "labels": status_labels,
                "data": status_data
            },
            "kpis": kpis
        }

        return {
            "kpis": kpis, 
            "dashboard_json": dashboard_json
        }
    
class TreasurerDashboardService:
    def __init__(self, dashboard_repo):
        self.repo = dashboard_repo

    def _normalize_rows_to_labels_data(self, rows, label_col='label', value_col='total_amount_collected'):
        """
        Normalize repository return values into {"labels": [...], "data": [...]}.

        Accepted inputs:
          - None -> {"labels": [], "data": []}
          - dict already shaped -> returns a copy
          - list of dicts -> uses dict[label_col], dict[value_col]
          - list of tuples -> uses tuple[0], tuple[1]
          - single scalar / unexpected shapes -> returns empty lists

        Ensures numbers in data are floats (safe-cast with fallback 0.0).
        """
        if rows is None:
            return {"labels": [], "data": []}

        # Already shaped
        if isinstance(rows, dict):
            if 'labels' in rows and 'data' in rows:
                return {
                    "labels": list(rows.get('labels') or []),
                    "data": [float(v or 0) for v in (rows.get('data') or [])]
                }
            # Maybe repo returned {"rows": [...]}
            if 'rows' in rows and isinstance(rows['rows'], (list, tuple)):
                rows = rows['rows']
            else:
                # unexpected dict shape
                return {"labels": [], "data": []}

        # If rows is a single row (tuple/dict), convert to list
        if isinstance(rows, (tuple, dict)):
            rows = [rows]

        labels = []
        data = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    lbl = r.get(label_col)
                    val = r.get(value_col)
                else:
                    # Tuple-like
                    try:
                        lbl = r[0]
                        val = r[1]
                    except Exception:
                        # unexpected shape, skip
                        continue

                labels.append(lbl)
                try:
                    data.append(float(val) if val is not None else 0.0)
                except Exception:
                    # catch e.g. 'Tue' or other bad values
                    data.append(0.0)
        except Exception:
            return {"labels": [], "data": []}

        return {"labels": labels, "data": data}

    def get_dashboard_content(self) -> dict:
        # KPIs
        kpi_pending_payments = self.repo.fetch_kpi_pending_payments()
        kpi_sub_pending_payments = self.repo.fetch_kpi_sub_pending_payments()
        kpi_or_issued_this_week = self.repo.fetch_kpi_official_receipts_issued_this_week()
        kpi_sub_or_issued_this_week = self.repo.fetch_kpi_sub_official_receipts_issued_this_week()
        kpi_collections_this_week = self.repo.fetch_kpi_collections_this_week()
        kpi_sub_collections_this_week = self.repo.fetch_kpi_sub_collections_this_week()
        kpi_collections_this_year = self.repo.fetch_kpi_collections_this_year()
        kpi_sub_collections_this_year = self.repo.fetch_kpi_sub_collections_this_year()

        kpis = {
            "pending_payments": kpi_pending_payments,
            "pending_payments_delta": kpi_sub_pending_payments,
            "or_issued_this_week": kpi_or_issued_this_week,
            "or_issued_this_week_delta": kpi_sub_or_issued_this_week,
            "collections_this_week": kpi_collections_this_week,
            "collections_this_week_delta": kpi_sub_collections_this_week,
            "collections_this_year": kpi_collections_this_year,
            "collections_this_year_delta": kpi_sub_collections_this_year,
        }

        # Collections trend (last 7 days)
        collections_trend_raw = self.repo.fetch_collections_trend_last_7_days()
        collections_trend = self._normalize_rows_to_labels_data(
            collections_trend_raw,
            label_col='label',
            value_col='total_amount_collected'
        )

        # Collections per month (current year)
        collections_per_month_raw = self.repo.fetch_collections_per_month()
        collections_per_month = self._normalize_rows_to_labels_data(
            collections_per_month_raw,
            label_col='month_label',
            value_col='total_amount_collected'
        )

        dashboard_json = {
            "collectionsTrend": {
                "labels": collections_trend.get("labels", []),
                "data": collections_trend.get("data", [])
            },
            "collectionsPerMonth": {
                "labels": collections_per_month.get("labels", []),
                "data": collections_per_month.get("data", [])
            }
        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json
        }
