from dependency_injector import containers, providers

from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.app.services.scheduling_service import SchedulingService

class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()

    scheduling_service: providers.Factory[ISchedulingService] = providers.Factory(
        SchedulingService,
        scheduling_repository=infra.active_schedules
    )