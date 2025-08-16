from src.core.contracts.infra.family_membership import IFamilyMembershipRepository
from src.core.value_objects.family_membership import FamilyMembership


class FamilyMembershipService:

    def __init__(self, repository: IFamilyMembershipRepository):
        self.repository = repository

    def execute(
            self,
            resident_id: int,
            household_id: int,
            family_id: int,
            household_head_relationship: int,
            family_head_relationship: int,
            residency_period: int) -> str:
        data = self.__retrieve_resident_data(resident_id, household_id, family_id)
        membership = FamilyMembership(**data)
        membership.validate_membership_request()
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

    def __retrieve_resident_data(self, resident_id, household_id, family_id):
        membership_count = self.repository.find_resident_per_household(
            resident_id)
        household_id = self.repository.get_household_id(household_id)
        is_household_active = self.repository.get_household_active_status(
            household_id)
        family_id = self.repository.get_family_unit_id(family_id)
        is_family_active = self.repository.get_family_active_status(family_id)
        resident_id = self.repository.get_resident_id(resident_id)
        return {
            "resident_id": resident_id,
            "household_id": household_id,
            "family_id": family_id,
            "is_household_active": is_household_active,
            "is_family_active": is_family_active,
            "membership_count": membership_count
        }