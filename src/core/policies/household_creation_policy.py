from src.core.entities.resident import Resident
from src.core.exceptions.policy_exception import PolicyException
from src.core.policies.resident_eligibility_policy import ResidentEligibilityPolicy


class HouseholdCreationPolicy:
    
    def __init__(self, resident: Resident):
        self.resident = resident

    def verify_eligibility(
        self, 
        household_number_count: int, 
        request: int, 
        house_number_req_count: int):

        ResidentEligibilityPolicy(self.resident).check_eligibility()

        if household_number_count > 0:
            raise PolicyException("Household already exists.")

        if house_number_req_count > 0:
            raise PolicyException("House number is already requested.")
        
        if request > 0:
            raise PolicyException("You already have a pending household creation request.")