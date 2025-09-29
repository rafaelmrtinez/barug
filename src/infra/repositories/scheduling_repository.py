from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO
from src.infra.contracts.connection_adapter import IConnectionAdapter


class ActiveScheduleRepository:
    
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        
    def sort_by_status(self, status: int) -> list[ActiveScheduleDTO]:
        raw = """
        SELECT 
        hi.household_id,
        bs.schedule_id AS "Schedule ID",
        INITCAP(
            TRIM(
                REGEXP_REPLACE(
                    CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name),
                    '\s+', ' ', 'g'
                )
            )
        ) || 
        COALESCE(' ' || p.suffix, '') || 
        '''s Household' AS "Household Name",
        cw.week_label || ', ' || cw.year_num AS "Week Range",
        rs.request_status_name AS "Status"
        FROM bhw_schedule bs
        INNER JOIN household_info hi ON hi.household_id = bs.household_id 
        INNER JOIN person p ON p.person_id = hi.household_head_id
        INNER JOIN calendar_week cw ON cw.week_id = bs.week_id
        INNER JOIN request_status rs ON rs.request_status_id = bs.status
        WHERE rs.request_status_id = %s;
        """
        params = [status]
        rows = self._ctx.execute_query(raw, params)
        return [ActiveScheduleDTO(*row) for row in rows]
        
    def search_schedule(self, search_key: str) -> list[ActiveScheduleDTO]:
        sql = """
            SELECT 
            hi.household_id,
            bs.schedule_id AS "Schedule ID",
            INITCAP(TRIM(REGEXP_REPLACE(CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name), '\s+', ' ', 'g')))
                || COALESCE(' ' || p.suffix, '') || '''s Household' AS "Household Name",
            cw.week_label || ', ' || cw.year_num AS "Week Range",
            rs.request_status_name AS "Status"
            FROM bhw_schedule bs
            INNER JOIN household_info hi ON hi.household_id = bs.household_id 
            INNER JOIN person p ON p.person_id = hi.household_head_id
            INNER JOIN calendar_week cw ON cw.week_id = bs.week_id
            INNER JOIN request_status rs ON rs.request_status_id = bs.status
            WHERE CAST(bs.schedule_id AS TEXT) = %s
            OR cw.week_label ILIKE %s
            OR rs.request_status_name ILIKE %s
            OR INITCAP(TRIM(REGEXP_REPLACE(CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name), '\s+', ' ', 'g')))
                    || COALESCE(' ' || p.suffix, '') ILIKE %s;
        """
        params = [search_key, f"%{search_key}%", f"%{search_key}%", f"%{search_key}%"]
        rows = self._ctx.execute_query(sql, params)
        return [ActiveScheduleDTO(*row) for row in rows]
    
    def sort_by_week_range(self, week_range: int) -> list[ActiveScheduleDTO]:
        raw = """
        SELECT 
        hi.household_id,
        bs.schedule_id AS "Schedule ID",
        INITCAP(
            TRIM(
                REGEXP_REPLACE(
                    CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name),
                    '\s+', ' ', 'g'
                )
            )
        ) || 
        COALESCE(' ' || p.suffix, '') || 
        '''s Household' AS "Household Name",
        cw.week_label || ', ' || cw.year_num AS "Week Range",
        rs.request_status_name AS "Status"
        FROM bhw_schedule bs
        INNER JOIN household_info hi ON hi.household_id = bs.household_id 
        INNER JOIN person p ON p.person_id = hi.household_head_id
        INNER JOIN calendar_week cw ON cw.week_id = bs.week_id
        INNER JOIN request_status rs ON rs.request_status_id = bs.status
        WHERE cw.week_id = %s;
        """
        params = [week_range]
        rows = self._ctx.execute_query(raw, params)
        return [ActiveScheduleDTO(*row) for row in rows]
        
    def fetch_schedules(self) -> list[ActiveScheduleDTO]:
        raw = """
        SELECT 
        hi.household_id,
        bs.schedule_id AS "Schedule ID",
        INITCAP(
            TRIM(
                REGEXP_REPLACE(
                    CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name),
                    '\s+', ' ', 'g'
                )
            )
        ) || 
        COALESCE(' ' || p.suffix, '') || 
        '''s Household' AS "Household Name",
        cw.week_label || ', ' || cw.year_num AS "Week Range",
        rs.request_status_name AS "Status"
        FROM bhw_schedule bs
        INNER JOIN household_info hi ON hi.household_id = bs.household_id 
        INNER JOIN person p ON p.person_id = hi.household_head_id
        INNER JOIN calendar_week cw ON cw.week_id = bs.week_id
        INNER JOIN request_status rs ON rs.request_status_id = bs.status;
        """
        return [ActiveScheduleDTO(*row) for row in self._ctx.execute_query(raw)]