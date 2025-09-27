from src.infra.contracts.connection_adapter import IConnectionAdapter


class SchedulingRepository:
    
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        
    def fetch_schedules(self):
        raw = """
        SELECT 
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
        return self._ctx.execute_query(raw)