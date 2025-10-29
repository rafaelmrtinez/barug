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