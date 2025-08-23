from dataclasses import dataclass
import uuid
from src.core.exceptions.domain_exceptions import DomainException

@dataclass(frozen=True)
class HouseholdNumber:
    """This value object is used to enforce business rules
    for Household Number.
    
    Raises:
        DomainException: Household number is not valid
    """
    
    household_number: str
    is_unique: bool
    
    def __post_init__(self):
        self.__validate_household_number()
    
    def __validate_household_number(self):
        if not self.household_number:
            self.household_number = str(uuid.uuid4())

        if not self.household_number.isdigit():
            raise DomainException("Household number must be a valid numeric string.")
        
        if len(self.household_number) < 1 or len(self.household_number) > 20:
            raise DomainException("Household number must be between 1 and 20 characters.")

        if not self.is_unique:
            raise DomainException("Household number must be unique.")