from dataclasses import dataclass

from src.core.exceptions.domain_exceptions import DomainException


@dataclass
class HouseholdHead:
    id: str
    name: str
    
    def __post_init__(self):
        if not self.id or not self.name:    
            raise DomainException("Household head is empty or non existent.")