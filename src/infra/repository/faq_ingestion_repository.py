from postgrest.exceptions import APIError


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.core.contracts.faq_repo import IFAQIngestionRepository


class FAQIngestionRepository(IFAQIngestionRepository):
    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter.get_client()
        
    def insert_faq_document(self, file_name: str, total_faqs: int, uploader: str) -> None:
        response = self.supabase_adapter.table('faq_document').insert({
            "title": file_name,
            "total_faqs": total_faqs,
            "uploaded_by": uploader
        }).execute()
        return response.data[0]['id']

    
    def insert_bulk_faq_entries(self, entries: list[dict]) -> None:
        response = self.supabase_adapter.table('faq_entry').insert(entries).execute()
        return response.data[0]['document_id']