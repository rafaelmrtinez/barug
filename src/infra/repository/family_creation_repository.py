from postgrest.exceptions import APIError

from src.app.transfer_objects.data.household_info import HouseholdInformationDTO
from src.app.transfer_objects.persistence.family_creation import FamilyCreationPersistence
from src.app.utils.dob_utility import DateOfBirthUtility
from src.core.contracts.infra.repository.family_creation import IFamilyCreationRepository
from src.core.entities.resident import Resident
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.exceptions.supabase_sdk.pending_request import PendingRequestException



class FamilyCreationRepository(IFamilyCreationRepository):
    
    def __init__(self, client: SupabaseAdapter):
        self.client = client.client
        
    def find_existing_family_number_request(self, ufc_number: str):
        res = (
            self.client.table('family_creation_req')
            .select(count='exact')
            .eq('ufc_num', ufc_number).execute()
        )
        return res.count
        
    def insert_family_unit(self, persistence: 'FamilyCreationPersistence'):
        func = 'insert_family_creation_request'
        try:
            result = (
            self.client.rpc(fn=func, params={
            'p_requester_id': persistence.requester_id,
            'p_existing_household_id': persistence.household_id,
            'p_family_num': persistence.family_number,
            'p_ucf_num': persistence.ucf_number,
            'p_source_of_income': persistence.source_of_income,
            'p_family_mnthly_income_id': persistence.family_monthly_income,
            'p_nhts_status_id': persistence.nhts_status,
            'p_indigent_status_id': persistence.indigent_status,
            'p_household_type_id': persistence.house_type,
            'p_relationship_to_hholdhead_id': persistence.household_head_relationship
            }).execute()
            )
            return result.data
        except APIError as e:
            if str(e.message) == "This person already has a pending family creation request." and str(e.code) == "P5032":
                raise PendingRequestException("This person already has a pending family creation request.")
            if str(e.message) == "You already have a pending request to join a household." and str(e.code) == "P5035":
                raise PendingRequestException("You already have a pending request to join a household.")
            raise e
        
    def get_existing_family_number_request_count(self, family_number: str):
        res = (
            self.client
            .table('family_unit')
            .select(count='exact')
            .eq('family_num', family_number).execute()
        )
        return res.count

    def find_pending_request(self, requester_id: int) -> int:
        result = (
            self.client.table('family_creation_req').select(count='exact').eq('requested_by', requester_id).execute()
        )
        return result.count if result.count else 0

    def get_all_family_count(self):
        result = (
            self.client.table('family_unit')
            .select(count='exact')
            .execute()
        )
        

        return result.count if result.count else 0
    
    def get_family_count_by_household_id(self, id):
        result = (
            self.client.table('family_unit')
            .select('family_id', count='exact')
            .eq('household_id', id)
            .execute()
        )
        if not result.data:
            return None
        return result.count if result.count else 0
    
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
    
    def get_household_info_by_house_num(self, house_num: str) -> HouseholdInformationDTO:
        result = (
            self.client
            .table('household_info')
            .select('household_id, house_number, house_type(house_type_id)')
            .eq('house_number', house_num)
            .execute()
        )
        
        if not result.data:
            return None
        
        data = HouseholdInformationDTO(
            household_id=result.data[0]['household_id'],
            house_type_id=result.data[0]['house_type']['house_type_id'],
            house_number=result.data[0]['house_number']
        )
        return data if result.data else None

    def find_resident_family_unit_if_exist(self, id):
        result = (
            self.client.table('house_member').select(count='exact').eq('person_id', id).execute()
        )
        return True if result.count else False