from dependency_injector import containers, providers

from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.repositories.household_info_repository import HouseholdInfoRepository
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository

from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository
)
from src.infra.repositories.business_repository import (
    BusinessRepository,
    ResidentOwnerRepository
)


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

    business: providers.Factory[IBusinessRepository] = providers.Factory(
        BusinessRepository,
        ctx=context
    )

    resident_owner: providers.Factory[IResidentOwnerRepository] = providers.Factory(
        ResidentOwnerRepository,
        ctx=context
    )

    business_registration_service: providers.Provider[IBusinessRepository] = providers.Factory(
        BusinessRepository,
        ctx=context
    )