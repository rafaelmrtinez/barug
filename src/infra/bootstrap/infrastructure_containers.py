from dependency_injector import containers, providers

from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.repositories.scheduling_repository import SchedulingRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    context = providers.Object(None)
    
    active_schedules: providers.Factory[ISchedulingRepository] = providers.Factory(
        SchedulingRepository,
        ctx=context
    )