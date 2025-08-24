from dataclasses import dataclass
import uuid

from src.core.enums.person_status import PersonStatus
from src.core.enums.relationship import Relationships
from src.core.enums.resident_status import ResidentStatus
from src.core.exceptions.domain_exceptions import DomainException
from src.core.exceptions.policy_exception import PolicyException


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
        
    def is_of_legal_age(self):
        return True if self.age >= 18 else False
    
    def is_active(self):
        return True if self.status == PersonStatus.ACTIVE.value else False
        
    def is_resident(self):
        print(f'Residential status: {self.residential_status}')
        return True if self.residential_status == ResidentStatus.RESIDENT.value else False