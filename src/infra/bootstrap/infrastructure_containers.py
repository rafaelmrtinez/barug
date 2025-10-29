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
from src.infra.repositories.scheduling_repository import ActiveScheduleRepository
from src.infra.repositories.week_range_repository import WeekRangeRepository


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

    active_schedules: providers.Factory[ISchedulingRepository] = providers.Factory(
        ActiveScheduleRepository,
        ctx=context,
    )

    week_range_repository: providers.Factory[IWeekRangeRepository] = providers.Factory(
        WeekRangeRepository,
        ctx=context,
    )
    