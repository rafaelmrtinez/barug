from dependency_injector import containers, providers

# app-level service contracts
from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.contracts.child_services import IChildService
from src.app.contracts.child_health_service import IChildHealthService
from src.app.contracts.household_info_service import IHouseholdInformationService
from src.app.contracts.maternal_service import IMaternalService
from src.app.contracts.scheduling_service import ISchedulingService
from src.app.contracts.maternal_schedule_service import IMaternalScheduleService
from src.app.contracts.maternal_postpartum_service import IMaternalPostpartumService
from src.app.contracts.maternal_status_service import IMaternalRecordStatusService
from src.app.contracts.laboratory_service import ILaboratoryService
from src.app.contracts.image_download_service import IImageDownloadService
from src.app.contracts.child_health_schedule_service import IChildHealthScheduleService

# concrete service implementations
from src.app.services.antenatal_service import AntenatalCareService
from src.app.services.child_services import ChildService
from src.app.services.child_health_services import ChildHealthService
from src.app.services.household_info_service import HouseholdInformationService
from src.app.services.maternal_service import MaternalService
from src.app.services.scheduling_service import SchedulingService
from src.app.services.maternal_schedule_service import MaternalScheduleService
from src.app.services.maternal_postpartum_service import MaternalPostpartumService
from src.app.services.maternal_status_service import MaternalRecordStatusService
from src.app.services.laboratory_service import LaboratoryService
from src.app.services.image_download_service import ImageDownloadService
from src.app.services.faq_ingestion_service import FAQIngestionService
from src.app.services.child_health_schedule_service import ChildHealthScheduleService


from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
    IBusinessRenewalService,
    IBusinessRenewalQuoteService,
    IBusinessRenewalRequestService,
    IBusinessClosurePaymentRequestService,
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
    BusinessRenewalQuoteService,
    BusinessRenewalRequestService,
    BusinessClosurePaymentRequestService,
)
from src.app.contracts.household_service_contract import (
    IHouseholdService
)
from src.app.services.household_service import (
    HouseholdService
)
from src.app.services.dashboards_service import (
    ClerkDashboardService,
    TreasurerDashboardService,
    CaptainDashboardService,
    SecretaryDashboardService,
    LuponMemberDashboardService,
    BhwDashboardService,
    MidwifeDashboardService,
)


from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
    IBusinessRenewalService,
    IBusinessRenewalQuoteService,
    IBusinessRenewalRequestService,
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
    BusinessRenewalQuoteService,
    BusinessRenewalRequestService,
)
from src.app.contracts.household_service_contract import (
    IHouseholdService
)
from src.app.services.household_service import (
    HouseholdService
)


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""

    config = providers.Configuration()

    infra = providers.DependenciesContainer()

    antenatal_care_service: providers.Factory[IAntenatalCareService] = providers.Factory(
        AntenatalCareService,
        anc_repository=infra.antenatal_care_repository,
    )

    child_service: providers.Factory[IChildService] = providers.Factory(
        ChildService,
        child_repository=infra.child_repository,
    )

    child_health_service: providers.Factory[IChildHealthService] = providers.Factory(
        ChildHealthService,
        ch_repo=infra.child_health_repository,
    )

    maternal_service: providers.Factory[IMaternalService] = providers.Factory(
        MaternalService,
        maternal_repository=infra.maternal_repository,
        family_repository=infra.family_repository,
    )

    household_info_service: providers.Factory[IHouseholdInformationService] = providers.Factory(
        HouseholdInformationService,
        household_info_repository=infra.household_info_repository,
    )

    scheduling_service: providers.Factory[ISchedulingService] = providers.Factory(
        SchedulingService,
        scheduling_repository=infra.active_schedules,
    )

    maternal_schedule_service: providers.Factory[IMaternalScheduleService] = providers.Factory(
        MaternalScheduleService,
        repository=infra.maternal_health_record_repository,
    )

    maternal_postpartum_service: providers.Factory[IMaternalPostpartumService] = providers.Factory(
        MaternalPostpartumService,
        repository=infra.maternal_health_record_repository,
    )

    maternal_status_service: providers.Factory[IMaternalRecordStatusService] = providers.Factory(
        MaternalRecordStatusService,
        repository=infra.maternal_health_record_repository,
    )

    laboratory_service: providers.Factory[ILaboratoryService] = providers.Factory(
        LaboratoryService,
        repository=infra.maternal_health_record_repository,
        staff_id=providers.Dependency(),
        record_id=providers.Dependency(),
    )

    image_download_service: providers.Factory[IImageDownloadService] = providers.Factory(
        ImageDownloadService,
        repository=infra.maternal_health_record_repository,
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

    business_renewal_request_service: providers.Factory[IBusinessRenewalRequestService] = providers.Factory(
        BusinessRenewalRequestService,
        repo=infra.business_renewal_request
    )

    business_closure_payment_request_service: providers.Factory[IBusinessClosurePaymentRequestService] = providers.Factory(
        BusinessClosurePaymentRequestService,
        repo=infra.business_closure_payment_request,
    )

    # FAQ ingestion service
    faq_ingestion_service = providers.Factory(
        FAQIngestionService,
        repository=infra.faq_ingestion_repository,
    )

    # Dashboard Services can be added here in the app container as needed
    clerk_dashboard_service: providers.Factory[ClerkDashboardService] = providers.Factory(
        ClerkDashboardService,
        dashboard_repo=infra.clerk_dashboard_repository,
    )

    treasurer_dashboard_service: providers.Factory[TreasurerDashboardService] = providers.Factory(
        TreasurerDashboardService,
        dashboard_repo=infra.treasurer_dashboard_repository,
    )

    captain_dashboard_service: providers.Factory[CaptainDashboardService] = providers.Factory(
        CaptainDashboardService,
        dashboard_repo=infra.captain_dashboard_repository,
    )

    secretary_dashboard_service: providers.Factory[SecretaryDashboardService] = providers.Factory(
        SecretaryDashboardService,
        dashboard_repo=infra.secretary_dashboard_repository,
    )

    lupon_mem_dashboard_service: providers.Factory[LuponMemberDashboardService] = providers.Factory(
        LuponMemberDashboardService,
        dashboard_repo=infra.lupon_mem_dashboard_repository,
    )

    bhw_dashboard_service: providers.Factory[BhwDashboardService] = providers.Factory(
        BhwDashboardService,
        dashboard_repo=infra.bhw_dashboard_repository,
    )

    midwife_dashboard_service: providers.Factory[MidwifeDashboardService] = providers.Factory(
        MidwifeDashboardService,
        dashboard_repo=infra.midwife_dashboard_repository,
    )
    
    # Child health schedule service (thin orchestration service)
    child_health_schedule_service: providers.Factory[IChildHealthScheduleService] = providers.Factory(
        ChildHealthScheduleService,
        repo=infra.child_health_record_repository,
    )
