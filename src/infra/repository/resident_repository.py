from src.app.utils.dob_utility import DateOfBirthUtility
from src.core.contracts.infra.repository.resident_repository import IResidentRepository
from src.core.entities.resident import Resident
from src.infra.adapter.supabase_adapter import SupabaseAdapter


class ResidentRepository(IResidentRepository):

    def __init__(self, client: SupabaseAdapter):
        self.client = client.client

    def get_resident_by_id(self, id: str) -> "Resident":
        result = (
            self.client.table('person').select(
                'person_id, first_name, middle_name, last_name, birthdate, person_status(person_status_id), residential_status(residential_status_id)'
            ).eq('person_id', id).execute()
        )
        if not result.data:
            return None
        full_name = str(f"{result.data[0]['first_name']} {result.data[0]['middle_name'] if result.data[0]['middle_name'] else '' } {result.data[0]['last_name']}").lower()
        return Resident(
            id=id,
            name=full_name,
            status=int(result.data[0]['person_status']['person_status_id']),
            residential_status=int(result.data[0]['residential_status']['residential_status_id']),
            age=DateOfBirthUtility().calculate_exact_age(result.data[0]['birthdate'])
        )