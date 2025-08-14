# from src.core.contracts.infra.family_membership import IFamilyMembershipRepository
from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository

class FamilyMembershipService:
    
    def __init__(self, repository: FamilyMembershipRepository):
        self.repository = repository
        
    def execute(
        self, 
        resident_id: str, 
        household_id: str, 
        family_id: str,
        household_head_relationship: int, 
        family_head_relationship: int, 
        residency_period: int) -> str:
        self.__validate_resident_existence(resident_id)
        self.__validate_household_and_family_unit_integrity(household_id, family_id)
        self.__validate_resident_membership(resident_id)
        request_id = self.repository.join_family_unit({
            'p_requester_id': resident_id,
            'p_family_id': family_id,
            'p_relationship_to_hholdhead_id': household_head_relationship,
            'p_relationship_to_family_head_id': family_head_relationship,
            'p_residency_period': residency_period
        })
        if not request_id:
            raise ValueError("Unable to join family at the moment.")
        return "OK"

    def __validate_resident_membership(self, resident_id):
        _resident_membership = self.repository.find_resident_per_household(resident_id)
        if _resident_membership > 0:
            raise ValueError('Unable to proceed request, dual membership found.')

    def __validate_household_and_family_unit_integrity(self, household_id, family_id):
        _household_id = self.repository.get_household_id(household_id)
        if not _household_id:
            raise ValueError("Household does not exist.")

        is_household_active = self.repository.get_household_active_status(household_id)
        if not is_household_active:
            raise ValueError("Household is no longer active.")
        
        _family_id = self.repository.get_family_unit_id(family_id)
        if not _family_id:
            raise ValueError('Family does not exist.')

        is_family_active = self.repository.get_family_active_status(family_id)
        if not is_family_active:
            raise ValueError('Family unit is no longer active.')

    def __validate_resident_existence(self, resident_id):
        _resident_id = self.repository.get_resident_id(resident_id)
        if not _resident_id:
            raise ValueError("Resident does not exist")