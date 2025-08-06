from abc import ABC, abstractmethod
from ast import List

class IRAGRepository(ABC):
    """
    Interface for AI repository operations.
    """
    
    @abstractmethod
    def get_faq_document_id_order_by_date(self) -> int:
        """
        Retrieve the most recent FAQ document ID ordered by upload date.
        """
        pass
    
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