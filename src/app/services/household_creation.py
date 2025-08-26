import datetime
import pytz

from resident.transfer_obj.household_creation_request import CreateHouseholdRequest
from src.app.contracts.household_creation import IHouseholdCreationService
from src.core.contracts.infra.repository.household_creation import IHouseholdCreationRepository
from src.core.contracts.infra.repository.resident_repository import IResidentRepository
from src.core.value_objects.household_number import HouseholdNumber
from src.core.policies.household_creation_policy import HouseholdCreationPolicy
from src.core.policies.resident_eligibility_policy import ResidentEligibilityPolicy
from src.core.utils.household_number_generator import IdentificationGenerator
from src.infra.transfer_obj.household_creation_persistence import HouseholdCreationPersistence


class HouseholdCreationService(IHouseholdCreationService):

    def __init__(
            self,
            repo: IHouseholdCreationRepository,
            resident_repo: IResidentRepository):
        self.repo = repo
        self.resident_repo = resident_repo

    def execute(self, req: CreateHouseholdRequest) -> dict:
        house_number_count = self.repo.find_household_by_house_number(req.house_number)
        request = self.repo.get_existing_request_count_by_id(req.resident_id)
        house_number_req_count = self.repo.get_existing_house_number_request(req.house_number)
        resident = self.resident_repo.get_resident_by_id(req.resident_id)

        HouseholdCreationPolicy(resident=resident).verify_eligibility(
            household_number_count=house_number_count,
            request=request,
            house_number_req_count=house_number_req_count
        )

        current_time = datetime.datetime.now(pytz.timezone('Asia/Manila'))
        household_number = HouseholdNumber.create(
            house_number=req.house_number,
            date=current_time,
            exists=lambda candidate: self.repo.get_existing_household_num_request(candidate)
        )

        data = HouseholdCreationPersistence(
            p_requester_id=req.resident_id,
            p_household_num=household_number.value,
            p_house_number=req.house_number,
            p_household_req_desc=req.message,
            p_house_type_id=req.house_type,
            p_house_ownership_id=req.house_ownership,
            p_city=req.city,
            p_barangay=req.barangay,
            p_sitio_purok=req.sitio,
            p_street=req.street,
            p_is_hhold_head=True
        )
        
        return self.repo.create_household(data.__dict__)
