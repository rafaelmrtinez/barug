from abc import ABC, abstractmethod


class IFAQIngestionRepository(ABC):
    
    @abstractmethod
    def insert_bulk_faq_entries(self, entries: list[dict]) -> None:
        """
        Insert multiple FAQ entries in a single request.
        Each entry should be a dict with keys: question, answer, embedding, document_id
        """
        pass