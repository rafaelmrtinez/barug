from dependency_injector import containers, providers

from src.core.contracts.ai_repository import IAIRepository
from src.core.contracts.document_repository import IDocumentRepository
from src.core.contracts.embedding import IEmbedding
from src.core.contracts.llm import ILLM
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.gateways.groq_client import GroqClient
from src.infra.gateways.hf_embedding import HuggingFaceClient
from src.infra.repository.ai_repository import AIRepository
from src.infra.repository.ai_repository import AIRepository
from src.infra.repository.document_repository import DocumentRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()

    supabase_adapter = providers.Object(None)

    document_repository: providers.Factory[
        IDocumentRepository
        ] = providers.Factory(
            DocumentRepository,
            supabase_adapter=supabase_adapter
    )

    ai_repository: providers.Factory[IAIRepository] = providers.Factory(
        AIRepository,
        supabase_adapter=supabase_adapter,
    )

    hf_embedding: providers.Singleton[IEmbedding] = providers.Singleton(
        HuggingFaceClient,
        provider=config.HF_PROVIDER,
        api_key=config.HF_API_KEY,
        model=config.HF_MODEL
    )

    groq_client: providers.Singleton[ILLM] = providers.Singleton(
        GroqClient,
        api_key=config.AI_API_KEY,
        model=config.AI_MODEL
    )
