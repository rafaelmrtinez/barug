from dependency_injector import containers, providers

from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.repositories.household_info_repository import HouseholdInfoRepository
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    context = providers.Object(None)
    
    household_info = providers.Factory(
        HouseholdInfoRepository,
        ctx=context
    )
    
    active_schedules: providers.Factory[ISchedulingRepository] = providers.Factory(
        ActiveScheduleRepository,
        ctx=context
    )
    