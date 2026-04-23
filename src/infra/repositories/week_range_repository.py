from src.infra.database.connection_adapter import ConnectionAdapter
from src.domain.contracts.week_range_repository import IWeekRangeRepository


class WeekRangeRepository(IWeekRangeRepository):
    def __init__(self, ctx: ConnectionAdapter) -> None:
        self._ctx = ctx

    def get_all(self) -> list[tuple]:
        query = "SELECT week_id, week_label || ', ' || year_num AS week_range FROM calendar_week;"
        result = self._ctx.execute_query(query)
        return result