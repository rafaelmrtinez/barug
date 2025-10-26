from dependency_injector import containers, providers

from src.app.contracts.household_info_service_contract import IHouseholdInfoService
from src.app.contracts.scheduling_service_contract import ISchedulingService
from src.app.services.household_info_service import HouseholdInformationService
from src.app.services.scheduling_service import SchedulingService

from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
    IBusinessRenewalService,
    IBusinessRenewalQuoteService
)
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository
)
from src.app.services.business_service import (
    BusinessService,
    ResidentOwnerService,
    BusinessRegistrationService,
    OwnerBusinessInfoService,
    BusinessRenewalService,
    BusinessRenewalQuoteService
)
from src.app.contracts.household_service_contract import (
    IHouseholdService
)
from src.app.services.household_service import (
    HouseholdService
)


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""

    # wiring_config = containers.WiringConfiguration(
    #     modules=["clerk.views.business"]   # 👈 THIS matches your file path
    # )
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()

    household_info_service: providers.Factory[IHouseholdInfoService]  = providers.Factory(
        HouseholdInformationService,
        household_info_repository=infra.household_info
    )

    scheduling_service: providers.Factory[ISchedulingService] = providers.Factory(
        SchedulingService,
        scheduling_repository=infra.active_schedules
    )

    business_service: providers.Factory[IBusinessService] = providers.Factory(
        BusinessService,
        business_repository=infra.business
    )

    resident_owner_service: providers.Factory[IResidentOwnerService] = providers.Factory(
        ResidentOwnerService,
        resident_owner_repository=infra.resident_owner
    )

    business_registration_service: providers.Provider[IBusinessRegistrationService] = providers.Factory(
        BusinessRegistrationService,
        registration_repo=infra.business_registration_service
    )

    owner_business_service= providers.Factory(
        OwnerBusinessInfoService,
        owner_business_repo=infra.owner_business_info,
        storage_repo=infra.storage
    )

    business_repository = infra.business
    # resident_owner_repository = infra.resident_owner

    household_service: providers.Provider[IHouseholdService] = providers.Factory(
        HouseholdService,
        household_repository=infra.household_list
    )

    household_repository: providers.Provider[IHouseholdRepository] = infra.household_list

    business_renewal_service: providers.Factory[IBusinessRenewalService] = providers.Factory(
        BusinessRenewalService,
        business_renewal_repo=infra.business_renewal
    )

    business_renewal_quote_service: providers.Factory[IBusinessRenewalQuoteService] = providers.Factory(
        BusinessRenewalQuoteService,
        quote_repo=infra.business_renewal_quote
    )
