from dependency_injector import containers, providers

from src.app.contracts.household_info_service_contract import IHouseholdInfoService
from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.app.services.household_info_service import HouseholdInformationService
from src.app.services.maternal_service import MaternalService
from src.app.services.scheduling_service import SchedulingService
from src.infra.repositories import maternal_repository

class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()
    
    maternal_service = providers.Factory(
        MaternalService,
        maternal_repository=infra.maternal_repository,
        family_repository=infra.family_repository
    )

    household_info_service: providers.Factory[IHouseholdInfoService]  = providers.Factory(
        HouseholdInformationService,
        household_info_repository=infra.household_info
    )

    scheduling_service: providers.Factory[ISchedulingService] = providers.Factory(
        SchedulingService,
        scheduling_repository=infra.active_schedules
    )