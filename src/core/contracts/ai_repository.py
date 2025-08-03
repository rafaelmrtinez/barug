from abc import ABC, abstractmethod
from ast import List

class IAIRepository(ABC):
    """
    Interface for AI repository operations.
    """
    
    @abstractmethod
    def exec_semantic_search(func_name: str,
    embedding: list[float],
    threshold: float,
    top_k: int,
    doc_id: str) -> list[dict]:
        """
        Executes a function call with the given name and parameters.
        """
        pass