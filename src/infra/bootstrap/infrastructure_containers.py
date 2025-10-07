from dependency_injector import containers, providers

from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.repositories.family_repository import FamilyRepository
from src.infra.repositories.household_info_repository import HouseholdInfoRepository
from src.infra.repositories.maternal_repository import MaternalRepository
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    context = providers.Object(None)
    
    family_repository: providers.Factory[IFamilyRepository] = providers.Factory(
        FamilyRepository,
        ctx=context
    )

    maternal_repository: providers.Factory[IMaternalRepository] = providers.Factory(
        MaternalRepository,
        ctx=context
    )
    
    household_info = providers.Factory(
        HouseholdInfoRepository,
        ctx=context
    )
    
    active_schedules: providers.Factory[ISchedulingRepository] = providers.Factory(
        ActiveScheduleRepository,
        ctx=context
    )
    