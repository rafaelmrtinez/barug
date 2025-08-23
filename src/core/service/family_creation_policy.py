from src.core.entities.resident import Resident
from src.core.enums.relationship import Relationships
from src.core.exceptions.family_policy_exception import FamilyPolicyException


class FamilyCreationPolicy:
    def __init__(self, resident: Resident):
        self.resident = resident

    def ensure_eligibility(
        self, 
        household_number: int, 
        household_head_relationship: str, 
        has_existing_household: bool, 
        pending_requests: int) -> None:
        
        if not household_number:
            raise FamilyPolicyException("Household number does not exist.")
        
        if not self.resident.is_resident():
            raise FamilyPolicyException("Resident is not registered in the barangay.")

        if not self.resident.is_active():
            raise FamilyPolicyException("Resident is not active.")

        if not self.resident.is_of_legal_age():
            raise FamilyPolicyException("Resident is not of legal age to request family creation.")

        print(f'Has existing household result {has_existing_household}')
        if has_existing_household:
            raise FamilyPolicyException("Resident is already part of another family unit.")

        if household_head_relationship not in Relationships.relationship_list():
            raise FamilyPolicyException("Invalid household head relationship.")
        
        # if pending_requests > 0:
        #     raise FamilyPolicyException("There is already a pending family creation request for this resident.")