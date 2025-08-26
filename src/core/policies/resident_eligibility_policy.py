from src.core.entities.resident import Resident
from src.core.exceptions.policy_exception import PolicyException


class ResidentEligibilityPolicy:
    
    def __init__(self, resident: Resident):
        self.resident = resident
        
    def check_eligibility(self, has_existing_household: bool):
        if not self.resident.is_resident():
            raise PolicyException("Resident is not registered in the barangay.")

        if not self.resident.is_active():
            raise PolicyException("Resident is not active.")

        if not self.resident.is_of_legal_age():
            raise PolicyException("Resident is not of legal age to request family creation.")
        
        if has_existing_household:
            raise PolicyException("Resident is already part of another family unit.")