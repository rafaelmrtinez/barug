from typing import List
from src.core.contracts.ai_repository import IAIRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException


class AIRepository(IAIRepository):

    def __init__(self, supabase_adapter: SupabaseAdapter):
        self.supabase_adapter = supabase_adapter.client

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
            return self.supabase_adapter.rpc(func_name, params).execute().data
        except Exception as e:
            raise DataAccessException(f"Failed to execute semantic search: {str(e)}")