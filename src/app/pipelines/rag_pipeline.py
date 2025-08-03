from typing import List
from src.app.dto.semantic_search import SemanticSearchDTO
from src.app.utils.rag_pipeline_utils import RAGPipelineUtils
from src.core.contracts.ai_repository import IAIRepository
from src.core.contracts.document_repository import IDocumentRepository
from src.core.contracts.embedding import IEmbedding
from src.core.contracts.llm import ILLM

class RAGPipeline:

    def __init__(
        self, 
        embedding: IEmbedding, 
        repos: IAIRepository, 
        llm: ILLM,
        doc_repo: IDocumentRepository
        ) -> None:
        """
        Initializes the RAG pipeline with the necessary components.
        """
        self.llm = llm
        self.repos = repos
        self.doc_repo = doc_repo
        self.embedding = embedding
        self.pipeline_utility = RAGPipelineUtils()
        
    def exec(self, prompt: str) -> str:
        embedding = self.__generate_embedding(prompt)
        doc_id = self.doc_repo.get_faq_document_id_order_by_date()
        top_k = self.__semantic_search(embedding, threshold=0.7, top_k=3, doc_id=doc_id)
        filtered_context = self.__extract_top_k_content(top_k)
        context = self.__extract_larger_content(prompt, filtered_context)
        return self.llm.generate_text(context)

    def __generate_embedding(self, prompt: str) -> List[float]:
        """
        Generates an embedding for the given prompt using the embedding service.
        """
        return self.embedding.generate_embedding(prompt)

    def __semantic_search(self, embedding: List[float], threshold: float, top_k: int, doc_id: str) -> List[dict]:
        """
        Performs a semantic search using the provided embedding.
        """
        return self.repos.exec_semantic_search('match_faq_entries', embedding, threshold, top_k, doc_id=doc_id)

    def __extract_larger_content(self, query: str, top_k: List[str]) -> str:
        """ 
        Extracts larger content based on the query and top-k results.
        """
        return self.pipeline_utility.extract_larger_content(query, top_k)
        
    def __extract_top_k_content(self, data: List[dict]) -> List[SemanticSearchDTO]:
        """
        Extracts top-k content from the semantic search results.
        """
        return self.pipeline_utility.extract_top_k_content(data)
