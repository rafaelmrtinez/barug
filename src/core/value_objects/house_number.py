from dataclasses import dataclass

from src.core.exceptions.domain_exceptions import DomainException


@dataclass(frozen=True)
class HouseNumber:
    """
    This value object is used to enforce business rules
    for House Number.
    """

    house_number: str
    is_exist: bool
    is_unique: bool
    
    def __post_init__(self):
        
        if not self.house_number:
            raise DomainException('House number is required.')
        
        if not self.house_number.isdigit():
            raise DomainException('House number must be a valid numeric string.')
        
        if not (1 <= len(self.house_number) <= 20):
            raise DomainException('House number must be between 1 and 20 characters.')
        
        if not self.is_exist:
            raise DomainException(f'No record of current {self.house_number} found.')

        if not self.is_unique:
            raise DomainException(f'An existing House Number for {self.house_number} already exists.')