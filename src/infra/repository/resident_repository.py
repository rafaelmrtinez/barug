from src.app.utils.dob_utility import DateOfBirthUtility
from src.core.entities.resident import Resident
from src.core.value_objects import date_of_birth
from src.core.value_objects.date_of_birth import DateOfBirth
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.data_access_exception import DataAccessException


class ResidentRepository:

    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
        
    def get_family_head_existence(self, id):
        result = (
            self.client.table('family_unit').select('family_head_id', count='exact').eq('family_head_id', id).execute()
        )
        if not result.data:
            raise DataAccessException('Something went wrong - Resident Repository at get_family_head_existence')
        return True if result.count > 0 else False

    def get_resident_age_by_id(self, id) -> DateOfBirth:
        result = (
            self.client.table('person').select(
                'date_of_birth'
            ).eq('person_id', id).execute()
        )
        if not result.data:
            return None
        dob = DateOfBirthUtility().calculate_exact_age(result.data[0]['date_of_birth'])
        return DateOfBirth(
            date_of_birth=dob
        )

    def get_resident_by_id(self, id: str) -> Resident:
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
