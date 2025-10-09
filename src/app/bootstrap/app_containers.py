from dependency_injector import containers, providers

from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.contracts.child_services import IChildService
from src.app.services.antenatal_service import AntenatalCareService
from src.app.services.child_services import ChildService
from src.domain.contracts.household_info_service_contract import IHouseholdInfoService
from src.domain.contracts.scheduling_service_contract import ISchedulingService
from src.app.services.household_info_service import HouseholdInformationService
from src.app.services.maternal_service import MaternalService
from src.app.services.scheduling_service import SchedulingService
from src.domain.contracts.maternal_service import IMaternalService

class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()
    
    antenatal_care_service: providers.Factory[IAntenatalCareService] = providers.Factory(
        AntenatalCareService,
        anc_repository=infra.antenatal_care_repository
    )
    
    child_service: providers.Factory[IChildService] = providers.Factory(
        ChildService,
        child_repository=infra.child_repository
    )

    maternal_service: providers.Factory[IMaternalService] = providers.Factory(
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