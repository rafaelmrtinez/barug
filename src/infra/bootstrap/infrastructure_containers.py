from dependency_injector import containers, providers

# domain contracts
from src.domain.contracts.account_status_repository import IAccountStatusRepository
from src.domain.contracts.antenatal_care_repository import IAntenatalCareRepository
from src.domain.contracts.child_health_record_repository import IChildHealthRecordRepository
from src.domain.contracts.child_health_repository import IChildHealthRepository
from src.domain.contracts.child_repository import IChildRepository as IDomainChildRepository
from src.domain.contracts.family_repository import IFamilyRepository
from src.domain.contracts.household_info_repository import IHouseholdInfoRepository
from src.domain.contracts.maternal_health_record_repository import IMaternalHealthRecordRepository
from src.domain.contracts.maternal_repository import IMaternalRepository
from src.domain.contracts.scheduling_repository_contract import ISchedulingRepository
from src.domain.contracts.week_range_repository import IWeekRangeRepository

# concrete infra repositories
from src.infra.repositories.account_status_repository import AccountStatusRepository
from src.infra.repositories.antenatal_care_repository import AntenatalCareRepository
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.infra.repositories.child_health_repository import ChildHealthRepository
from src.infra.repositories.child_repository import ChildRepository
from src.infra.repositories.family_repository import FamilyRepository
from src.infra.repositories.household_info_repository import HouseholdInfoRepository
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.repositories.maternal_repository import MaternalRepository
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.infra.repositories.child_report_repository import ChildReportRepository
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository
from src.infra.repositories.week_range_repository import WeekRangeRepository
from src.infra.storage.supabase_storage import SupabaseStorage
from authentication.supabase_client import supabase

from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
    IBusinessRenewalRepository,
    IBusinessRenewalQuoteRepository,
    IBusinessRenewalRequestRepository,
    IBusinessClosurePaymentRequestRepository,
)
from src.infra.repositories.business_repository import (
    BusinessRepository,
    ResidentOwnerRepository,
    OwnerBusinessInformationRepository,
    BusinessRenewalRepository,
    BusinessRenewalQuoteRepository,
    BusinessRenewalRequestRepository,
    BusinessClosurePaymentRequestRepository,
)
from src.infra.gateways.faq_ingestion_gateway import FAQIngestionGateway
from src.domain.contracts.household_repository_contract import (
    IHouseholdRepository,
)
from src.infra.repositories.household_repository import (
    HouseholdRepository,
)
from src.infra.repositories.dashboards_repository import (
    ClerkDashboardRepository,
    TreasurerDashboardRepository,
)


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    context = providers.Object(None)

    account_status_repository: providers.Factory[IAccountStatusRepository] = providers.Factory(
        AccountStatusRepository,
        context=context,
    )

    antenatal_care_repository: providers.Factory[IAntenatalCareRepository] = providers.Factory(
        AntenatalCareRepository,
        context=context,
    )

    child_health_record_repository: providers.Factory[IChildHealthRecordRepository] = providers.Factory(
        ChildHealthRecordRepository,
        ctx=context,
    )

    child_health_repository: providers.Factory[IChildHealthRepository] = providers.Factory(
        ChildHealthRepository,
        ctx=context,
    )

    child_repository: providers.Factory[IDomainChildRepository] = providers.Factory(
        ChildRepository,
        ctx=context,
    )

    family_repository: providers.Factory[IFamilyRepository] = providers.Factory(
        FamilyRepository,
        ctx=context,
    )

    household_info_repository: providers.Factory[IHouseholdInfoRepository] = providers.Factory(
        HouseholdInfoRepository,
        ctx=context,
    )

    maternal_health_record_repository: providers.Factory[IMaternalHealthRecordRepository] = providers.Factory(
        MaternalHealthRecordRepository,
        ctx=context,
    )

    maternal_repository: providers.Factory[IMaternalRepository] = providers.Factory(
        MaternalRepository,
        ctx=context,
    )

    # provider for report generation repository (used by maternal report API/service)
    maternal_report_repository = providers.Factory(
        MaternalReportRepository,
        ctx=context,
    )

    # provider for child report generation repository (added)
    child_report_repository = providers.Factory(
        ChildReportRepository,
        ctx=context,
        child_health_repo=child_health_record_repository,
    )

    # FAQ ingestion repo (external function caller)
    faq_ingestion_repository = providers.Factory(
        FAQIngestionGateway,
    )

    supabase_client = providers.Object(supabase)
    
    household_info = providers.Factory(
        HouseholdInfoRepository,
        ctx=context
    )
    
    active_schedules: providers.Factory[ISchedulingRepository] = providers.Factory(
        ActiveScheduleRepository,
        ctx=context,
    )

    week_range_repository: providers.Factory[IWeekRangeRepository] = providers.Factory(
        WeekRangeRepository,
        ctx=context,
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

    business_renewal_request: providers.Factory[IBusinessRenewalRequestRepository] = providers.Factory(
        BusinessRenewalRequestRepository,
        ctx=context
    )

    business_closure_payment_request: providers.Factory[IBusinessClosurePaymentRequestRepository] = providers.Factory(
        BusinessClosurePaymentRequestRepository,
        ctx=context
    )

    # Dashboards Repositories can be added here in the infra container as needed

    clerk_dashboard_repository: providers.Factory[ClerkDashboardRepository] = providers.Factory(
        ClerkDashboardRepository,
        ctx=context,
    )

    treasurer_dashboard_repository: providers.Factory[TreasurerDashboardRepository] = providers.Factory(
        TreasurerDashboardRepository,
        ctx=context,
    )
