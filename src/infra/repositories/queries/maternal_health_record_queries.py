from src.infra.contracts.connection_adapter import IConnectionAdapter


class MaternalHealthRecordQueries:
    
    def __init__(self, connection: IConnectionAdapter):
        self._connection = connection
    
    def get_by_maternal_health_record_id(self, maternal_health_record_id: int) -> dict | None:
        """Return the maternal health record row as a dict for the given id.

        Returns None when no row is found.
        """
        sql = "SELECT * FROM maternal_health_record WHERE maternal_health_record_id = %s"
        try:
            rows = self._connection.execute_query_to_dict(sql, (maternal_health_record_id,))
            if rows:
                return rows[0]
            return None
        except Exception:
            # Let caller handle/log exceptions
            raise