from src.app.transfer_objects.commands.family_creation import FamilyCreationCommand
from src.app.transfer_objects.persistence.family_creation import FamilyCreationPersistence
from src.app.contracts.family_creation_service import IFamilyCreationService
from src.core.contracts.infra.repository.family_creation import IFamilyCreationRepository
from src.core.entities.resident import Resident
from src.core.service.family_creation_policy import FamilyCreationPolicy


class FamilyCreationService(IFamilyCreationService):
    def __init__(self, family_creation_repo: IFamilyCreationRepository):
        self.family_creation_repo = family_creation_repo

    def execute(self, cmd: FamilyCreationCommand) -> int:
        household_info = self.family_creation_repo.get_household_info_by_house_num(cmd.household_number)
        house_type = household_info.house_type_id
        resident: Resident = self.family_creation_repo.get_resident_by_id(cmd.requester_id)
        has_existing_household: bool = self.family_creation_repo.find_resident_family_unit_if_exist(cmd.requester_id)
        pending_requests = self.family_creation_repo.get_pending_request(cmd.requester_id)
        
        FamilyCreationPolicy(resident).ensure_eligibility(
            household_info.household_id,
            cmd.household_head_relationship,
            has_existing_household,
            pending_requests
        )

        family_count_by_household = self.family_creation_repo.get_family_count_by_household_id(id=household_info.household_id)
        total_family_count = self.family_creation_repo.get_all_family_count()

        family_number = f"HH{household_info.household_id}-FAM00{family_count_by_household + 1}"
        ucf_number = f"UFC-{household_info.household_id}-{total_family_count + 1}"

        return (self.family_creation_repo
                .create_family_unit(
                    FamilyCreationPersistence(
                        requester_id=cmd.requester_id,
                        household_id=household_info.household_id,
                        family_number=family_number,
                        ucf_number=ucf_number,
                        source_of_income=cmd.source_of_income,
                        family_monthly_income=cmd.family_monthly_income,
                        nhts_status=cmd.nhts_status,
                        indigent_status=cmd.indigent_status,
                        house_type=house_type,
                        household_head_relationship=cmd.household_head_relationship
                    )))
