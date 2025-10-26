from dependency_injector import containers, providers

from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.infra.repositories.household_info_repository import HouseholdInfoRepository
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository
from src.infra.storage.supabase_storage import SupabaseStorage
from authentication.supabase_client import supabase

from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
    IBusinessRenewalRepository,
    IBusinessRenewalQuoteRepository,
)
from src.infra.repositories.business_repository import (
    BusinessRepository,
    ResidentOwnerRepository,
    OwnerBusinessInformationRepository,
    BusinessRenewalRepository,
    BusinessRenewalQuoteRepository
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)
from src.infra.repositories.household_repository import (
    HouseholdRepository,
)


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    context = providers.Object(None)
    supabase_client = providers.Object(supabase)
    
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

    owner_business_info= providers.Factory(
        OwnerBusinessInformationRepository,
        ctx=context
    )

    storage = providers.Factory(
        SupabaseStorage,
        _supabase=supabase_client
    )

    household_list: providers.Provider[IHouseholdRepository] = providers.Factory(
        HouseholdRepository,
        ctx=context
    )

    business_renewal:providers.Factory[IBusinessRenewalRepository] = providers.Factory(
        BusinessRenewalRepository,
        ctx=context
    )

    business_renewal_quote: providers.Factory[IBusinessRenewalQuoteRepository] = providers.Factory(
        BusinessRenewalQuoteRepository,
        ctx=context
    )
