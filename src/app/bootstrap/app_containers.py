from dependency_injector import containers, providers

from src.app.pipelines.rag_pipeline import RAGPipeline
from src.app.services.llm import LLMService


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()
    
    rag_pipeline = providers.Factory(
        RAGPipeline,
        repos=infra.ai_repository,
        embedding=infra.hf_embedding,
        llm=infra.groq_client,
        doc_repo=infra.document_repository
    )
    
    llm_service = providers.Factory(
        LLMService,
        rag_pipeline=rag_pipeline
    )