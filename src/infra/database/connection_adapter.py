from typing import Any, Sequence
from django.db import InternalError, connection

from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException


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
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except InternalError as e:
            orig = getattr(e, "__cause__", None)
            if orig is not None and hasattr(orig, "diag"):
                primary_message = orig.diag.message_primary
                code = orig.pgcode
            else:
                primary_message = str(e)
                code = None

            raise QueryExecutionException(primary_message, code)
        
    def execute_query_to_dict(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except InternalError as e:
            original_exception = getattr(e, "__cause__", None)
            raise QueryExecutionException(str(original_exception), original_exception.pgcode)
            
    def execute_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else None