import datetime
import pytz


from resident.transfer_obj.household_creation_request import CreateHouseholdRequest
from src.app.contracts.household_creation import IHouseholdCreationService
from src.core.contracts.infra.repository.household_creation import IHouseholdCreationRepository
from src.infra.transfer_obj.household_creation_persistence import HouseholdCreationPersistence


class HouseholdCreationService(IHouseholdCreationService):

    def __init__(self, repo: IHouseholdCreationRepository):
        self.repo = repo
        
    def execute(self, req: CreateHouseholdRequest) -> dict:
        # Check if house number exist, if not create a  new household
        house_number_count = self.repo.find_household_by_house_number(req.house_number)

        if house_number_count > 0:
            raise ValueError("House number already exists")
        
        current_time = datetime.datetime.now(pytz.timezone('Asia/Manila'))
        
        # generate household number
        household_number = f'HH-{req.house_number}-0{current_time.month}{str(current_time.year)[-2:]}'
        
        data = HouseholdCreationPersistence(
            p_requester_id=req.resident_id,
            p_household_num=household_number,
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