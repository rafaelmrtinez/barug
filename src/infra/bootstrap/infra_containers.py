from dependency_injector import containers, providers

from src.core.contracts.embedding import IEmbedding
from src.core.contracts.llm import ILLM
from src.infra.gateways.groq_client import GroqClient
from src.infra.gateways.hf_embedding import HuggingFaceClient

class InfraContainer(containers.DeclarativeContainer):
    
    config = providers.Configuration()
    
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