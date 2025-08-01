from dependency_injector import containers, providers

from src.app.services.llm import LLMService


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra = providers.DependenciesContainer()
    
    llm_service = providers.Factory(
        LLMService,
        chat=infra.groq_client
    )