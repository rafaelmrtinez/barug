from postgrest.exceptions import APIError


from src.core.contracts.rag_repository import IRAGRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException


class RAGRepository(IRAGRepository):

    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter.client
        
    def get_faq_document_id_order_by_date(self) -> int:
        """
        Retrieve a document by its ID.
        """
        try:
            response = self.supabase_adapter.table('faq_document').select('id').order(
                'uploaded_at', desc=True
                ).execute()
            
            if not response.data:
                raise DataAccessException("No documents found.")
            
            if not response.data[0].get('id'):
                raise DataAccessException("Document ID not found.")
            
            return response.data[0]['id']
        except APIError as e:
            raise DataAccessException(f"Failed to retrieve document: {str(e)}")

    def exec_semantic_search(
        self, 
        func_name: str, 
        embedding: list[float], 
        threshold: float, 
        top_k: int,
        doc_id: str
    ) -> list[dict]:
        """
        Executes a function call with the given name and parameters.
        """
        try:
            params = {
            'query_embedding': embedding,
            'match_threshold': threshold,
            'match_count': top_k,
            'target_document_id': doc_id
            }
            
            response = self.supabase_adapter.rpc(func_name, params).execute()
            
            if response.error:
                raise DataAccessException(f"Error executing semantic search: {response.error.message}")
            
            if not response.data:
                raise DataAccessException("No results found for the semantic search.")

            return response.data
        except Exception as e:
            raise DataAccessException(f"Failed to execute semantic search: {str(e)}")