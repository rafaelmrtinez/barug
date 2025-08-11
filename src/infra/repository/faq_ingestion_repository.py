from postgrest.exceptions import APIError


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.core.contracts.faq_repo import IFAQIngestionRepository
from src.infra.exceptions.data_access_exception import DataAccessException


class FAQIngestionRepository(IFAQIngestionRepository):
    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter.get_client()
        
    def insert_faq_document(self, file_name: str, total_faqs: int, uploader: str) -> None:
        try:
            response = self.supabase_adapter.table('faq_document').insert({
                "title": file_name,
                "total_faqs": total_faqs,
                "uploaded_by": uploader
            }).execute()
            
            if not response.data:
                raise DataAccessException("No data returned from insert operation.")
            
            if 'id' not in response.data[0]:
                raise DataAccessException("Inserted data does not contain 'id'.")
            
            return response.data[0]['id']
        except APIError as e:
            raise DataAccessException(f"Failed to insert FAQ document: {str(e)}")
    
    def insert_bulk_faq_entries(self, entries: list[dict]) -> None:
        """
        Insert multiple FAQ entries in a single Supabase request.
        Each entry should be a dict with keys: question, answer, embedding, document_id
        """
        try:
            response = self.supabase_adapter.table('faq_entry').insert(entries).execute()
            
            if not response.data:
                raise DataAccessException("No data returned from bulk insert operation.")
            
            if 'document_id' not in response.data[0]:
                raise DataAccessException("Inserted data does not contain 'document_id'.")
            
            return response.data[0]['document_id']
        except APIError as e:
            raise DataAccessException(f"API error occurred: {str(e)}")