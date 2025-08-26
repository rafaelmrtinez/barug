from src.core.contracts.infra.repository.household_creation import IHouseholdCreationRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.transfer_obj.household_creation_persistence import HouseholdCreationPersistence


class HouseholdCreationRepository(IHouseholdCreationRepository):

    def __init__(self, client: SupabaseAdapter):
        self.client = client.client

    def create_household(self, data: dict) -> dict:
        func = "insert_household_creation_request"
        res = (
            self.client
            .rpc(func, params=data)
            .execute()
        )
        return res.data

    def get_existing_house_number_request(self, house_number: str) -> int:
        res = (
            self.client
            .table("household_creation_req")
            .select(count="exact")
            .eq("house_number", house_number)
            .execute()
        )
        return res.count

    def get_all_household_count(self) -> int:
        res = (
            self.client
            .table("household_info")
            .select(count="exact")
            .execute()
        )
        return res.count
    
    def get_existing_request_count_by_id(self, id) -> int:
        res = (
            self.client
            .table("household_creation_req")
            .select(count="exact")
            .eq("requested_by_id", id)
            .execute()
        )
        return res.count
    
    def get_existing_household_num_request(self, household_num) -> int:
        res = (
            self.client
            .table("household_creation_req")
            .select(count="exact")
            .eq("household_num", household_num)
            .execute()
        )
        return res.count

    def find_household_by_house_number(self, house_no: str) -> int:
        res = (
            self.client
            .table("household_info")
            .select(count="exact")
            .eq("house_number", house_no)
            .execute()
        )
        return res.count
