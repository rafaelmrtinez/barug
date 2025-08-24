from dataclasses import dataclass
import uuid

from src.core.enums.person_status import PersonStatus
from src.core.enums.relationship import Relationships
from src.core.enums.resident_status import ResidentStatus
from src.core.exceptions.domain_exceptions import DomainException
from src.core.exceptions.family_policy_exception import FamilyPolicyException


@dataclass
class Resident:
    
    id: str
    name: str
    residential_status: int
    status: int
    age: int

    def __post_init__(self):
        
        if not self.id:
            self.id = uuid.uuid4()
            
        if not self.name:
            raise DomainException("Resident name is required.")
        
    def service_eligibility_check(self):
        
        """This method checks whether resident eligible for accessing barangay services

        Raises:
            FamilyPolicyException: Resident is not registered in the barangay.
            FamilyPolicyException: Resident is not active.
            FamilyPolicyException: Resident is not of legal age to request family creation.
        """
        
        if not self.is_resident():
            raise FamilyPolicyException("Resident is not registered in the barangay.")

        if not self.is_active():
            raise FamilyPolicyException("Resident is not active.")

        if not self.is_of_legal_age():
            raise FamilyPolicyException("Resident is not of legal age to request family creation.")
    
    def is_of_legal_age(self):
        return True if self.age >= 18 else False
    
    def is_active(self):
        return True if self.status == PersonStatus.ACTIVE.value else False
        
    def is_resident(self):
        print(f'Residential status: {self.residential_status}')
        return True if self.residential_status == ResidentStatus.RESIDENT.value else False