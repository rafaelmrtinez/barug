from src.core.contracts.app.family_service import IFamilyMembershipService
from src.core.contracts.infra.family_membership import IFamilyMembershipRepository
from src.core.value_objects.family_membership import FamilyMembership


class FamilyMembershipService(IFamilyMembershipService):

    def __init__(self, repository: IFamilyMembershipRepository):
        self.repository = repository

    def execute(
        self,
        years_of_residency: int,
        resident_id: int,
        household_id: int,
        family_id: int,
        household_head_relationship: int,
        family_head_relationship: int
    ) -> bool:
        data = self.__data_builder(
            resident_id,
            household_id,
            family_id,
            household_head_relationship,
            family_head_relationship
        )
        membership = FamilyMembership(**data)
        membership.validate_membership_request()
        request_id = self.repository.insert_membership({
            'p_requester_id': data.get('resident_id', None),
            'p_family_id': data.get('family_id', None),
            'p_relationship_to_hholdhead_id': household_head_relationship,
            'p_relationship_to_family_head_id': family_head_relationship,
            'p_residency_period': years_of_residency
        })
        return True if request_id else False

    def __data_builder(self, resident_id, household_id, family_id, household_head_relationship, family_head_relationship):
        data = self.__retrieve_resident_data(
            resident_id, household_id, family_id)
        data['household_head_relation'] = household_head_relationship
        data['family_head_relation'] = family_head_relationship
        return data

    def __retrieve_resident_data(self, resident_id: int, household_id: int, family_id: int):
        resident_data = self.repository.get_resident_basic_info(resident_id)
        household_data = self.repository.get_household_status(household_id)
        family_data = self.repository.get_family_unit_status(family_id)
        membership_count = self.repository.find_resident(resident_id)
        return {
            "resident_id": resident_data['person_id'],
            "household_id": household_data['household_id'],
            "family_id": family_data['family_id'],
            "is_household_active": household_data['is_active'],
            "is_family_active": family_data['is_active'],
            "membership_count": membership_count,
            "residential_status": resident_data['residential_status_id'],
            "person_status": resident_data['person_status_id'],
            "residency_period": resident_data['residency_period']
        }
