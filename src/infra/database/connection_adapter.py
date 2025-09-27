from typing import Any, Sequence
from django.db import connection

from src.infra.contracts.connection_adapter import IConnectionAdapter


class ConnectionAdapter(IConnectionAdapter):
    """
    Low-level SQL adapter. Should only be used in infra layer repositories.
    """

    def __init__(self, conn=connection):
        self.conn = conn

    def execute_command(self, sql: str, params: Sequence[Any] | None = None) -> int:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def execute_query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def execute_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else None