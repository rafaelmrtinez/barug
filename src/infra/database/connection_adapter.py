from typing import Any, Sequence, Optional, Tuple
from django.db import InternalError, connection

from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException
from src.infra.database.pg_error_extractor import PGErrorExtractor

import logging

logger = logging.getLogger(__name__)


class ConnectionAdapter(IConnectionAdapter):
    """
    Low-level SQL adapter. Should only be used in infra layer repositories.
    """

    def __init__(self, conn=connection):
        self.conn = conn

    def execute_command(self, sql: str, params: Sequence[Any] | None = None) -> int:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount
        except Exception as e:
            # Do not log SQL or params to avoid leaking secrets; log only exception type.
            logger.error("Database execute_command failed: %s", type(e).__name__)
            msg, code = PGErrorExtractor.extract(e)
            raise QueryExecutionException(msg, code) from e

    def execute_query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except Exception as e:
            # Avoid logging SQL or params which may contain sensitive data.
            logger.error("Database execute_query failed: %s", type(e).__name__)
            msg, code = PGErrorExtractor.extract(e)
            raise QueryExecutionException(msg, code) from e
        
    def execute_query_to_dict(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [col[0] for col in cursor.description] if cursor.description else []
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Database execute_query_to_dict failed: %s", type(e).__name__)
            msg, code = PGErrorExtractor.extract(e)
            raise QueryExecutionException(msg, code) from e
            
    def execute_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error("Database execute_scalar failed: %s", type(e).__name__)
            msg, code = PGErrorExtractor.extract(e)
            raise QueryExecutionException(msg, code) from e
