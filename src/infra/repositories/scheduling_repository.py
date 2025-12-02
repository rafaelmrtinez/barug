from django.db import InternalError
from src.app.transfer_objects.request.reschedule_cmd import RescheduleRequest
from src.app.transfer_objects.dto.active_schedule_dto import ActiveScheduleDTO
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException
from src.infra.exceptions.rescheduling_exception import ReschedulingException


class ActiveScheduleRepository(ISchedulingRepository):
    
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx
        
    def get_week_start_id_by_week_start_key(self, week_start: str)-> list[dict]:
        raw = """SELECT week_id FROM calendar_week WHERE week_start = %s;"""
        params = [week_start]
        result = self._ctx.execute_query_to_dict(raw, params)
        if not result:
            raise ReschedulingException("Selected week range does not exist.")
        return result[0]["week_id"]
        
    def insert_new_schedule(self, cmd: RescheduleRequest) -> list[dict] | None:
        try:
            raw = """SELECT * FROM reschedule_bhw_schedule(%s, %s, %s, %s);"""
            params = [
                cmd.p_schedule_id,
                cmd.p_new_week_id,
                cmd.p_resched_by_id,
                cmd.p_reason,
            ]
            res = self._ctx.execute_query(raw, params)
            
            if not res:
                raise ReschedulingException("Rescheduling failed, please try again.")
            return res[0][0]
        except QueryExecutionException as qe:
            if qe.code in ReschedulingException.ERROR_CODES:
                raise ReschedulingException(qe.message)
            print(f"Unexpected error during rescheduling: {qe.code} - {qe.message}")

    def sort_by_status(self, status: int) -> list[ActiveScheduleDTO]:
        raw = r"""
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
        sql = r"""
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
        raw = r"""
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
        raw = r"""
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