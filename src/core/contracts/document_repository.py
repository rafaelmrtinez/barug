from abc import ABC, abstractmethod


class IDocumentRepository(ABC):
    """
    Abstract base class for document repository interfaces.
    """
    
    @abstractmethod
    def save_document(self, document: dict) -> None:
        """
        Save a document to the repository.
        """
        pass
    
    @abstractmethod
    def get_document_by_id(self, document_id: str) -> dict:
        """
        Retrieve a document by its ID.
        """
        pass
    
    @abstractmethod
    def update_document(self, document_id: str, document: dict) -> None:
        """
        Update a document by its ID.
        """
        pass

    @abstractmethod
    def delete_document(self, document_id: str) -> None:
        """
        Delete a document by its ID.
        """
        pass