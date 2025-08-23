from src.core.contracts.app.service import IService
from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository
from src.core.entities.resident import Resident
from src.core.service.family_creation_policy import FamilyCreationPolicy
from src.infra.repository.family_creation_repository import FamilyCreationRepository
from src.infra.repository.resident_repository import ResidentRepository


class FamilyCreationService(IService):
    def __init__(
        self, 
        resident_repo: ResidentRepository, 
        household_repo: IHouseholdSearchRepository,
        family_creation_repo: FamilyCreationRepository):
        self.resident_repo = resident_repo
        self.household_repo = household_repo
        self.family_creation_repo = family_creation_repo

    def execute(self, **kwargs):
        requester_id = kwargs.get('user_id', None)
        household_number = kwargs.get('household_number', None)
        household_head_relationship = kwargs.get('household_head_relationship', None)
        
        
        indigent_status = kwargs.get('indigent_status', False)
        source_of_income = kwargs.get('source_of_income', None)
        family_monthly_income = kwargs.get('family_monthly_income', 0)
        nhts_status = kwargs.get('nhts_status', False)
        
        household_info = self.household_repo.get_household_info_by_house_num(household_number)
        resident: Resident = self.resident_repo.get_resident_by_id(requester_id)

        FamilyCreationPolicy(resident).ensure_eligibility(
            household_info['household_id'], 
            household_head_relationship,
            )

        family_count_by_household = self.household_repo.get_family_count_by_household_id(id=household_info['household_id'])
        total_family_count = self.household_repo.get_all_family_count()
        family_number = f'HH{household_info['household_id']}-FAM00{family_count_by_household + 1}'
        house_type = household_info['house_type']['house_type_name']
        ucf_number = f'UFC-{household_info['household_id']}-{total_family_count + 1}'
        
        data = {
            'p_requester_id': requester_id,
            'p_existing_household_id': household_info['household_id'],
            'p_family_number': family_number,
            'p_ucf_num': ucf_number,
            'p_source_of_income': source_of_income,
            'family_monthly_income_id': family_monthly_income,
            'nhts_status_id': nhts_status,
            'p_indigent_status': indigent_status,
            'p_household_type_id': house_type,
            'p_relation_to_hholdhead_id': household_head_relationship
        }

        return self.family_creation_repo.create_family_unit(data)
