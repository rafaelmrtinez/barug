from src.infra.contracts.connection_adapter import IConnectionAdapter


class ChildMonitoringQuery:

    def __init__(self, db: IConnectionAdapter):
        self._db = db

    def fetch_by_child_record_id(self, child_record_id: int) -> list[dict]:
        """Return all monitoring rows for a given child_record_id ordered by
        check_date (newest first) then child_monitoring_id desc.

        Returns a list of dicts with keys matching the table columns.
        """
        sql = """
        SELECT
            child_monitoring_id,
            check_date::date AS check_date,
            age,
            weight,
            temperature,
            height,
            findings,
            notes,
            child_record_id,
            visit_id
        FROM public.child_monitoring_log
        WHERE child_record_id = %s
        ORDER BY check_date DESC NULLS LAST, child_monitoring_id DESC;
        """
        params = [child_record_id]
        rows = self._db.execute_query_to_dict(sql, params)
        return rows or []

    def fetch_latest_by_child_record_id(self, child_record_id: int) -> dict | None:
        """Return the single most recent monitoring row for a child, or None.

        Uses the same ordering as `fetch_by_child_record_id` but limits to one.
        """
        sql = """
        SELECT
            child_monitoring_id,
            check_date::date AS check_date,
            age,
            weight,
            temperature,
            height,
            findings,
            notes,
            child_record_id,
            visit_id
        FROM public.child_monitoring_log
        WHERE child_record_id = %s
        ORDER BY check_date DESC NULLS LAST, child_monitoring_id DESC
        LIMIT 1;
        """
        params = [child_record_id]
        rows = self._db.execute_query_to_dict(sql, params)
        return rows[0] if rows else None

    def fetch_by_monitoring_id(self, monitoring_id: int) -> dict | None:
        """Return a single monitoring row by its `child_monitoring_id`."""
        sql = """
        SELECT
            child_monitoring_id,
            check_date::date AS check_date,
            age,
            weight,
            temperature,
            height,
            findings,
            notes,
            child_record_id,
            visit_id
        FROM public.child_monitoring_log
        WHERE child_monitoring_id = %s
        LIMIT 1;
        """
        params = [monitoring_id]
        rows = self._db.execute_query_to_dict(sql, params)
        return rows[0] if rows else None