from dependency_injector import containers, providers

from src.core.contracts.llm import ILLM
from src.core.contracts.embedding import IEmbedding
from src.infra.gateways.groq_client import GroqClient
from src.core.contracts.rag_repository import IRAGRepository
from src.infra.gateways.hf_embedding import HuggingFaceClient
from src.infra.repository.rag_repository import RAGRepository
from src.core.contracts.faq_repo import IFAQIngestionRepository
from src.infra.repository.faq_ingestion_repository import FAQIngestionRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()

    supabase_adapter_dev = providers.Object(None)
    database = providers.Object(None)
    
    faq_entries_repository: providers.Factory[IFAQIngestionRepository] = providers.Factory(
        FAQIngestionRepository,
        supabase_adapter=supabase_adapter_dev
    )

    rag_repository: providers.Factory[IRAGRepository] = providers.Factory(
        RAGRepository,
        supabase_adapter=supabase_adapter_dev,
    )

    embedding: providers.Singleton[IEmbedding] = providers.Singleton(
        HuggingFaceClient,
        provider=config.EMBEDDING_PROVIDER,
        api_key=config.EMBEDDING_API_KEY,
        model=config.EMBEDDING_MODEL,
        url=config.EMBEDDING_URL
    )

    llm_client: providers.Singleton[ILLM] = providers.Singleton(
        GroqClient,
        api_key=config.AI_API_KEY,
        model=config.AI_MODEL
    )
