from typing import Any, Sequence
from abc import ABC, abstractmethod

class IConnectionAdapter(ABC):
    
    @abstractmethod
    def execute_command(self, sql: str, params: Sequence[Any] | None = None) -> int:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def execute_query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        raise NotImplementedError("Subclasses must implement this method")
    
    @abstractmethod
    def execute_query_to_dict(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def execute_scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        raise NotImplementedError("Subclasses must implement this method")