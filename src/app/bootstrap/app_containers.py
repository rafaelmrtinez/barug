from dependency_injector import containers, providers

from src.app.pipelines.faq_ingestion_pipeline import FAQIngestionPipeline
from src.app.pipelines.rag_pipeline import RAGPipeline
from src.app.services.llm import LLMService


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()
    
    faq_ingestion_pipeline = providers.Factory(
        FAQIngestionPipeline,
        faq_entry_repo=infra.faq_entries_repository ,
        embedding=infra.embedding
    )
    
    rag_pipeline = providers.Factory(
        RAGPipeline,
        repos=infra.rag_repository,
        embedding=infra.embedding,
        llm=infra.llm_client,
    )
    
    llm_service = providers.Factory(
        LLMService,
        rag_pipeline=rag_pipeline
    )