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

    def get_child_by_maternal_record_id(self, maternal_health_record_id: int) -> dict | None:
        """Compatibility wrapper: resolve the mother (person_id) for the given
        `maternal_health_record_id` and return the most relevant child_health_record
        for that mother.

        This method preserves the previous API but delegates to
        `get_child_by_mother_id` which accepts a `mother_id` directly.
        """
        # Resolve the maternal health record to get the mother's person_id
        mhr = self.get_by_maternal_health_record_id(maternal_health_record_id)
        if not mhr:
            return None
        mother_id = mhr.get("person_id")
        if mother_id is None:
            return None
        return self.get_child_by_mother_id(mother_id)

    def get_child_by_mother_id(self, mother_id: int) -> dict | None:
        """Return the most relevant child_health_record row for the given `mother_id`.

        The method looks up rows in `child_health_record` where `mother_id` matches
        the provided value and returns the most recently created record (tiebreak
        by `child_record_id`). Returns None when no child record is found.
        """
        sql = (
            "SELECT c.* FROM child_health_record c "
            "WHERE c.mother_id = %s "
            "ORDER BY c.created_at DESC, c.child_record_id DESC "
        )
        try:
            rows = self._connection.execute_query_to_dict(sql, (mother_id,))
            return rows[0] if rows else None
        except Exception:
            # Let caller handle/log exceptions
            raise