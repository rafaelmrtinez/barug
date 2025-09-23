from dependency_injector import containers, providers

class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()