from src.core.contracts.document_repository import IDocumentRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException
from postgrest.exceptions import APIError


class DocumentRepository(IDocumentRepository):
    
    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter
    
    def insert_faq_document(self, file_name: str, total_faqs: int, uploader: str) -> None:
        try:
            return self.supabase_adapter.table('faq_document').insert({
                "title": file_name,
                "total_faqs": total_faqs,
                "uploaded_by": uploader
            }).execute()
        except APIError as e:
            raise DataAccessException(f"Failed to insert FAQ document: {str(e)}")
        
        
    
    def get_faq_document_id_order_by_date(self) -> int:
        """
        Retrieve a document by its ID.
        """
        try:
            return self.supabase_adapter.table('faq_document').select('id').order('uploaded_at', desc=True).execute().data[0]['id']
        except Exception as e:
            raise DataAccessException(f"Failed to retrieve document: {str(e)}")

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