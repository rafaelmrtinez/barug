class ClerkDashboardService:
    def __init__(
        self,
        dashboard_repo
    ):
        self.repo = dashboard_repo

    def get_dashboard_kpis(self) -> dict:
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