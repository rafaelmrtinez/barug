from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException
from postgrest.exceptions import APIError
from src.core.contracts.faq_repo import IFAQIngestionRepository


class FAQIngestionRepository(IFAQIngestionRepository):
    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter

    def insert_bulk_faq_entries(self, entries: list[dict]) -> None:
        """
        Insert multiple FAQ entries in a single Supabase request.
        Each entry should be a dict with keys: question, answer, embedding, document_id
        """
        try:
            response = self.supabase_adapter.get_client().table('faq_entry').insert(entries).execute()
            return response.data[0]['document_id']
        except APIError as e:
            raise DataAccessException(f"API error occurred: {str(e)}")