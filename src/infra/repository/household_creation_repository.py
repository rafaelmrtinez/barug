from src.core.contracts.infra.repository.household_creation import IHouseholdCreationRepository
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.transfer_obj.household_creation_persistence import HouseholdCreationPersistence


class HouseholdCreationRepository(IHouseholdCreationRepository):

    def __init__(self, client: SupabaseAdapter):
        self.client = client

    def create_household(self, data: dict) -> dict:
        func = "insert_household_creation_request"
        res = (
            self.client
            .rpc(func, params=data)
            .execute()
        )
        return res.data

    def find_household_by_house_number(self, house_no: str) -> int:
        res = (
            self.client
            .table("household_info")
            .select(count="exact")
            .eq("house_number", house_no)
            .execute()
        )
        return res.count
