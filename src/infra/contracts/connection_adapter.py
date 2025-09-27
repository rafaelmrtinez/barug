from typing import Any, Sequence


class IConnectionAdapter:
    
    def execute_command(self, sql: str, params: Sequence[Any] | None = None) -> int:
        raise NotImplementedError("Subclasses must implement this method")

    def execute_query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        raise NotImplementedError("Subclasses must implement this method")

    def execute_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        raise NotImplementedError("Subclasses must implement this method")