from postgrest.exceptions import APIError


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.core.contracts.document_repository import IDocumentRepository


class DocumentRepository(IDocumentRepository):
    
    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter
    
    def save_document(self, document: dict) -> None:
        """
        Save a document to the repository.
        """
        pass
    
    def get_document_by_id(self, document_id: str) -> dict:
        """
        Retrieve a document by its ID.
        """
        pass
    
    def update_document(self, document_id: str, document: dict) -> None:
        """
        Update a document by its ID.
        """
        pass

    def delete_document(self, document_id: str) -> None:
        """
        Delete a document by its ID.
        """
        pass