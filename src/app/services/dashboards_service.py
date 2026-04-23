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
    
class CaptainDashboardService:
    def __init__(self, dashboard_repo):
        self.repo = dashboard_repo

    def _normalize_rows_to_labels_data(self, rows, label_col='month_label', value_col='total_amount_collected'):
        """
        Minimal normalizer similar to TreasurerDashboardService._normalize_rows_to_labels_data.
        Accepts repo returns of several shapes and returns {"labels": [...], "data": [...]}.
        """
        if rows is None:
            return {"labels": [], "data": []}

        if isinstance(rows, dict) and 'labels' in rows and 'data' in rows:
            return {"labels": list(rows['labels']), "data": [float(v or 0) for v in rows['data']]}

        # If rows is a single dict/tuple -> wrap
        if isinstance(rows, (dict, tuple)):
            rows = [rows]

        labels = []
        data = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    lbl = r.get(label_col)
                    val = r.get(value_col)
                else:
                    # tuple-like: (label, value)
                    try:
                        lbl = r[0]
                        val = r[1]
                    except Exception:
                        continue
                labels.append(lbl)
                try:
                    data.append(float(val or 0))
                except Exception:
                    data.append(0.0)
        except Exception:
            return {"labels": [], "data": []}

        return {"labels": labels, "data": data}

    def get_dashboard_content(self) -> dict:
        ongoing_cases = self.repo.fetch_kpi_ongoing_cases()
        open_cases = self.repo.fetch_kpi_sub_ongoing_cases()

        # Residents KPIs
        total_residents = self.repo.fetch_kpi_total_residents()
        new_residents_month = self.repo.fetch_kpi_sub_total_residents()

        # Collections KPIs
        collections_week = self.repo.fetch_kpi_collections_this_week()
        collections_week_delta = self.repo.fetch_kpi_sub_collections_this_week()
        collections_year = self.repo.fetch_kpi_collections_this_year()
        collections_year_delta = self.repo.fetch_kpi_sub_collections_this_year()

        kpis = {
            "ongoing_cases": ongoing_cases,
            "open_cases": open_cases,
            "residents_total": total_residents,
            "new_residents_month": new_residents_month,
            "collections_this_week": collections_week,
            "collections_this_week_delta": collections_week_delta,
            "collections_this_year": collections_year,
            "collections_this_year_delta": collections_year_delta,
        }

        # Collections per month chart (current year)
        collections_per_month_raw = self.repo.fetch_collections_per_month()
        collections_per_month = self._normalize_rows_to_labels_data(
            collections_per_month_raw,
            label_col='month_label',
            value_col='total_amount_collected'
        )

        raw_case_nature_counts = self.repo.fetch_case_nature_counts()
        case_nature = self._normalize_rows_to_labels_data(
            [{"case_name": k, "case_count": v} for k, v in raw_case_nature_counts.items()],
            label_col='case_name',
            value_col='case_count'
        )

        dashboard_json = {
            "collectionsPerMonth": {
                "labels": collections_per_month.get("labels", []),
                "data": collections_per_month.get("data", [])
            },
            "casesNature": {
                "labels": case_nature.get("labels", []),
                "data": case_nature.get("data", [])
            }
        }

        return {
            "kpis": kpis, 
            "dashboard_json": dashboard_json
        }

class SecretaryDashboardService:
    def __init__(self, dashboard_repo):
        self.repo = dashboard_repo

    def _normalize_rows_to_labels_data(self, rows, label_col='month_label', value_col='total_amount_collected'):
        if rows is None:
            return {"labels": [], "data": []}

        if isinstance(rows, dict) and 'labels' in rows and 'data' in rows:
            return {"labels": list(rows['labels']), "data": [float(v or 0) for v in rows['data']]}

        # If rows is a single dict/tuple -> wrap
        if isinstance(rows, (dict, tuple)):
            rows = [rows]

        labels = []
        data = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    lbl = r.get(label_col)
                    val = r.get(value_col)
                else:
                    # tuple-like: (label, value)
                    try:
                        lbl = r[0]
                        val = r[1]
                    except Exception:
                        continue
                labels.append(lbl)
                try:
                    data.append(float(val or 0))
                except Exception:
                    data.append(0.0)
        except Exception:
            return {"labels": [], "data": []}

        return {"labels": labels, "data": data}


    def get_dashboard_content(self) -> dict:
        ongoing_cases = self.repo.fetch_kpi_ongoing_cases()
        open_cases = self.repo.fetch_kpi_sub_ongoing_cases()

        active_businesses = self.repo.fetch_kpi_active_biz()
        new_businesses_week = self.repo.fetch_kpi_sub_active_biz()

        demographic_households = self.repo.fetch_kpi_demographics()
        demographic_families = self.repo.fetch_kpi_sub_demographics()

        total_residents = self.repo.fetch_kpi_total_residents()
        new_residents_month = self.repo.fetch_kpi_sub_total_residents()

        kpis = {
            "ongoing_cases": ongoing_cases,
            "open_cases": open_cases,
            "active_businesses": active_businesses,
            "new_businesses_week": new_businesses_week,
            "household_total": demographic_households,
            "families_total": demographic_families,
            "residents_total": total_residents,
            "new_residents_month": new_residents_month,
        }

        raw_case_nature_counts = self.repo.fetch_case_nature_counts()
        case_nature = self._normalize_rows_to_labels_data(
            [{"case_name": k, "case_count": v} for k, v in raw_case_nature_counts.items()],
            label_col='case_name',
            value_col='case_count'
        )

        biz_status_counts = self.repo.fetch_biz_status_counts() 
        status_labels = ["ACTIVE", "PENDING", "CLOSED", "EXPIRED"]
        status_data = [biz_status_counts.get(s, 0) for s in status_labels]

        dashboard_json = {
            "casesNature": {
                "labels": case_nature.get("labels", []),
                "data": case_nature.get("data", [])
            },
            "statusBreakdown": {
                "labels": status_labels,
                "data": status_data
            },
        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json,
        }

class LuponMemberDashboardService:
    def __init__(self, dashboard_repo):
        self.repo = dashboard_repo

    def _normalize_rows_to_labels_data(self, rows, label_col='month_label', value_col='total_amount_collected'):
        if rows is None:
            return {"labels": [], "data": []}

        if isinstance(rows, dict) and 'labels' in rows and 'data' in rows:
            return {"labels": list(rows['labels']), "data": [float(v or 0) for v in rows['data']]}

        # If rows is a single dict/tuple -> wrap
        if isinstance(rows, (dict, tuple)):
            rows = [rows]

        labels = []
        data = []
        try:
            for r in rows:
                if isinstance(r, dict):
                    lbl = r.get(label_col)
                    val = r.get(value_col)
                else:
                    # tuple-like: (label, value)
                    try:
                        lbl = r[0]
                        val = r[1]
                    except Exception:
                        continue
                labels.append(lbl)
                try:
                    data.append(float(val or 0))
                except Exception:
                    data.append(0.0)
        except Exception:
            return {"labels": [], "data": []}

        return {"labels": labels, "data": data}

    def _rows_to_status_labels_and_counts(self, raw_rows):
        """
        Convert various shapes returned by the repo into ordered (labels, counts) lists
        - Accepts:
            * list of dicts: [{'settlement_status': 'SETTLED', 'case_count': 5}, ...]
            * list of tuples: [('SETTLED', 5), ...]
            * dict mapping: {'SETTLED': 5, ...}
        - Preserves order for list-like inputs. For dict mapping, uses insertion order.
        - Returns (labels_list, counts_list)
        """
        if raw_rows is None:
            return [], []

        # If mapping/dict: keys -> labels, values -> counts (preserve insertion order)
        if isinstance(raw_rows, dict):
            labels = []
            counts = []
            for k, v in raw_rows.items():
                labels.append(str(k))
                try:
                    counts.append(int(v or 0))
                except Exception:
                    counts.append(0)
            return labels, counts

        # If single-row dict/tuple, wrap it
        if isinstance(raw_rows, (dict, tuple)):
            raw_rows = [raw_rows]

        labels = []
        counts = []
        # List-like handling: preserve order
        for r in raw_rows:
            try:
                if isinstance(r, dict):
                    # prefer settlement_status column names commonly used
                    key = r.get('settlement_status') or r.get('settlement_status_name') or r.get('status') \
                          or next(iter(r.values()), None)
                    # prefer case_count or count-ish keys
                    val = r.get('case_count') or r.get('count') or r.get('case_count') or None
                    if val is None:
                        # try to pick the second value in the dict if present
                        vals = list(r.values())
                        val = vals[1] if len(vals) > 1 else vals[0] if vals else 0
                else:
                    # tuple-like / sequence
                    key = r[0] if len(r) > 0 else None
                    val = r[1] if len(r) > 1 else 0

                if key is None:
                    continue
                labels.append(str(key))
                try:
                    counts.append(int(val or 0))
                except Exception:
                    counts.append(0)
            except Exception:
                # skip malformed row but continue processing remaining rows
                continue

        return labels, counts

    def get_dashboard_content(self) -> dict:
        ongoing_cases = self.repo.fetch_kpi_ongoing_cases()
        open_cases = self.repo.fetch_kpi_sub_ongoing_cases()

        total_case_settled = self.repo.fetch_kpi_total_cases_settled()
        # total_case_settled_delta = self.repo.fetch_kpi_sub_total_cases_settled()

        total_case_unsettled = self.repo.fetch_kpi_total_cases_unsettled()
        # total_case_unsettled_delta = self.repo.fetch_kpi_sub_total_cases_unsettled()

        settlement_rate = self.repo.fetch_kpi_settlement_rate()

        kpis = {
            "ongoing_cases": ongoing_cases,
            "open_cases": open_cases,
            "total_case_settled": total_case_settled,
            # "total_case_settled_delta": total_case_settled_delta,
            "total_case_unsettled": total_case_unsettled,
            # "total_case_unsettled_delta": total_case_unsettled_delta,
            "settlement_rate": settlement_rate,
        }

        raw_case_nature_counts = self.repo.fetch_case_nature_counts()
        case_nature = self._normalize_rows_to_labels_data(
            [{"case_name": k, "case_count": v} for k, v in raw_case_nature_counts.items()],
            label_col='case_name',
            value_col='case_count'
        )

        settlement_status_raw = self.repo.fetch_settlement_status_counts()
        status_labels, status_data = self._rows_to_status_labels_and_counts(settlement_status_raw)

        # Define distinct colors for each settlement status
        status_color_map = {
            "SETTLED": "#2ecc71",  # Green
            "ARBITRATED": "#3498db",  # Blue
            "SETTLED THROUGH CONCILIATION": "#1abc9c",  # Turquoise
            "ISSUANCE OF CFA": "#9b59b6",  # Purple
            "DISMISSED – NON-APPEARANCE OF BOTH PARTIES": "#e74c3c",  # Red
            "ONGOING": "#f39c12",  # Orange
            "DISMISSED – NON-APPEARANCE OF COMPLAINANT": "#e67e22",  # Dark Orange
            "REPUDIATED": "#c0392b",  # Dark Red
            "SETTLED THROUGH MEDIATION": "#27ae60",  # Dark Green
            "FOR EXECUTION (SETTLEMENT)": "#16a085",  # Dark Turquoise
            "WITHDRAWN BY COMPLAINANT": "#8e44ad",  # Dark Purple
            "NOT SETTLED": "#95a5a6"  # Gray
        }
        
        # Assign colors based on labels
        status_colors = [status_color_map.get(label, "#34495e") for label in status_labels]

        dashboard_json = {
            "casesNature": {
                "labels": case_nature.get("labels", []),
                "data": case_nature.get("data", [])
            },
            "settlementStatus": {
                "labels": status_labels,
                "data": status_data,
                "colors": status_colors
            },
        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json,
        }

class BhwDashboardService:
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

    def get_dashboard_content(self, bhw_id: int | None = None) -> dict:
        ongoing_maternal_total= self.repo.fetch_kpi_ongoing_maternal_total()
        ongoing_maternal_total_sub = self.repo.fetch_kpi_sub_ongoing_maternal_total(bhw_id) if bhw_id is not None else 0
        visit_today_maternal = self.repo.fetch_kpi_visit_today_maternal()
        visit_today_postpartum = self.repo.fetch_kpi_visit_today_postpartum()
        visit_today_child = self.repo.fetch_kpi_visit_today_child()
        household_to_be_visited = self.repo.fetch_kpi_household_to_be_visited(bhw_id) if bhw_id is not None else 0
        total_residents = self.repo.fetch_kpi_demographic_residents()
        total_families = self.repo.fetch_kpi_demographic_families()
        total_households = self.repo.fetch_kpi_demographic_households()

        kpis = {
            "ongoing_maternal_total": ongoing_maternal_total,
            "ongoing_maternal_total_sub": ongoing_maternal_total_sub,
            
            "household_to_be_visited": household_to_be_visited,
            "residents_total": total_residents,
            "families_total": total_families,
            "household_total": total_households,
        }

        maternal_vax_per_month_raw = self.repo.fetch_maternal_vax_per_month()
        maternal_vax_per_month = self._normalize_rows_to_labels_data(
            maternal_vax_per_month_raw,
            label_col='month_label',
            value_col='women_vaccinated'
        )

        child_vax_per_month_raw = self.repo.fetch_children_vax_per_month()
        child_vax_per_month = self._normalize_rows_to_labels_data(
            child_vax_per_month_raw,
            label_col='month_label',
            value_col='unique_children_vaccinated'
        )

        dashboard_json = {
            "childvaxPerMonth": {
                "labels": child_vax_per_month.get("labels", []),
                "data": child_vax_per_month.get("data", [])
            },
            "maternalvaxPerMonth": {
                "labels": maternal_vax_per_month.get("labels", []),
                "data": maternal_vax_per_month.get("data", [])
            }
        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json,
        }
    
class MidwifeDashboardService:
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


    def get_dashboard_content(self, midwife_id: int | None = None) -> dict:
        ongoing_maternal_total= self.repo.fetch_kpi_ongoing_maternal_total()
        ongoing_maternal_total_sub = self.repo.fetch_kpi_sub_ongoing_maternal_total(midwife_id) if midwife_id is not None else 0
        visit_today_maternal = self.repo.fetch_kpi_visit_today_maternal()
        visit_today_postpartum = self.repo.fetch_kpi_visit_today_postpartum()
        visit_today_child = self.repo.fetch_kpi_visit_today_child()
        women_vaccinated = self.repo.fetch_kpi_women_vaccinated_this_week()
        children_vaccinated = self.repo.fetch_kpi_children_vaccinated_this_week()
        total_residents = self.repo.fetch_kpi_demographic_residents()
        total_families = self.repo.fetch_kpi_demographic_families()
        total_households = self.repo.fetch_kpi_demographic_households()

        kpis = {
            "ongoing_maternal_total": ongoing_maternal_total,
            "ongoing_maternal_total_sub": ongoing_maternal_total_sub,
            "visit_today_maternal": visit_today_maternal,
            "visit_today_postpartum": visit_today_postpartum,
            "visit_today_child": visit_today_child,
            "women_vaccinated": women_vaccinated,
            "children_vaccinated": children_vaccinated,
            "residents_total": total_residents,
            "families_total": total_families,
            "household_total": total_households,
        }

        maternal_vax_per_month_raw = self.repo.fetch_maternal_vax_per_month()
        maternal_vax_per_month = self._normalize_rows_to_labels_data(
            maternal_vax_per_month_raw,
            label_col='month_label',
            value_col='women_vaccinated'
        )

        child_vax_per_month_raw = self.repo.fetch_children_vax_per_month()
        child_vax_per_month = self._normalize_rows_to_labels_data(
            child_vax_per_month_raw,
            label_col='month_label',
            value_col='unique_children_vaccinated'
        )

        dashboard_json = {
            "childvaxPerMonth": {
                "labels": child_vax_per_month.get("labels", []),
                "data": child_vax_per_month.get("data", [])
            },
            "maternalvaxPerMonth": {
                "labels": maternal_vax_per_month.get("labels", []),
                "data": maternal_vax_per_month.get("data", [])
            }
        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json
        }
    
class AdminDashboardService:
    def __init__(self, dashboard_repo):
        self.repo = dashboard_repo

    def get_dashboard_content(self) -> dict:
        kpi_doc_req = self.repo.fetch_kpi_doc_req()
        kpi_sub_doc_req = self.repo.fetch_kpi_sub_doc_req()
        kpi_total_residents = self.repo.fetch_kpi_total_residents()
        ongoing_cases = self.repo.fetch_kpi_ongoing_cases()
        open_cases = self.repo.fetch_kpi_open_cases()
        demographic_households = self.repo.fetch_kpi_total_households()
        demographic_families = self.repo.fetch_kpi_total_families()
        women_vaccinated = self.repo.fetch_kpi_women_vaccinated_this_week()
        children_vaccinated = self.repo.fetch_kpi_children_vaccinated_this_week()

        kpis = {
            "doc_requests": kpi_doc_req,
            "doc_requests_delta": kpi_sub_doc_req,
            "residents_total": kpi_total_residents,
            "ongoing_cases": ongoing_cases,
            "open_cases": open_cases,
            "household_total": demographic_households,
            "families_total": demographic_families,
            "women_vaccinated": women_vaccinated,
            "children_vaccinated": children_vaccinated,
        }

        dashboard_json = {

        }

        return {
            "kpis": kpis,
            "dashboard_json": dashboard_json,
        }
        
