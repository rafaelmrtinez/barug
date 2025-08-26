from src.app.contracts.family_creation_service import IFamilyCreationService
from src.app.transfer_objects.commands.family_creation import FamilyCreationRequest
from src.app.transfer_objects.persistence.family_creation import FamilyCreationPersistence
from src.core.context.family_eligibility_context import FamilyEligibilityContext
from src.core.contracts.infra.repository.family_creation import IFamilyCreationRepository
from src.core.entities.resident import Resident
from src.core.policies.family_creation_policy import FamilyCreationPolicy
from src.core.utils.household_number_generator import IdentificationGenerator
from src.core.value_objects.family_number import FamilyNumber
from src.core.value_objects.ufc_number import UFCNumber


class FamilyCreationService(IFamilyCreationService):
    
    def __init__(self, family_creation_repo: IFamilyCreationRepository):
        self.family_creation_repo = family_creation_repo

    def execute(self, req: FamilyCreationRequest) -> int:
        resident: Resident = self.family_creation_repo.get_resident_by_id(req.requester_id)
        has_existing_household: bool = self.family_creation_repo.find_resident_family_unit_if_exist(req.requester_id)
        pending_requests = self.family_creation_repo.find_pending_request(req.requester_id)
        household_info = self.family_creation_repo.get_household_info_by_house_num(req.household_number)
        
        if not resident:
            raise ValueError('Resident does not exist.')
        
        if not household_info:
            raise ValueError('Household does not exist.')
        
        ctx = FamilyEligibilityContext(
            household_number=req.household_number,
            household_head_relationship=req.household_head_relationship,
            has_existing_household=has_existing_household,
            pending_requests=pending_requests
        )
        
        FamilyCreationPolicy(resident=resident, ctx=ctx).check_eligibility()

        total_family_count = self.family_creation_repo.get_all_family_count()
        family_count_by_household = self.family_creation_repo.get_family_count_by_household_id(id=household_info.household_id)

        ucf_number = UFCNumber.create(
            house_number=household_info.house_number, 
            family_count=family_count_by_household, 
            exists=self.family_creation_repo.find_existing_family_number_request).value
        
        
        family_number = FamilyNumber.create(
            house_number=household_info.house_number, 
            family_count=family_count_by_household, 
            exists=self.family_creation_repo.get_existing_family_number_request_count).value
        
        data = FamilyCreationPersistence(
                    requester_id=req.requester_id,
                    household_id=household_info.household_id,
                    family_number=family_number,
                    ucf_number=ucf_number,
                    source_of_income=req.source_of_income,
                    family_monthly_income=req.family_monthly_income,
                    nhts_status=req.nhts_status,
                    indigent_status=req
                    .indigent_status,
                    house_type=household_info.house_type_id,
                    household_head_relationship=req.household_head_relationship
                    )
        
        return self.family_creation_repo.insert_family_unit(data)
