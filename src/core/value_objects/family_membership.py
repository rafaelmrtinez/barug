from dataclasses import dataclass


from src.core.exceptions.domain_exceptions import DomainException


@dataclass(frozen=True)
class FamilyMembership:
    
    resident_id: int
    household_id: int
    family_id: int
    is_household_active: bool
    is_family_active: bool
    membership_count: int
        
    def validate_membership_request(self):
        self.__validate_resident_existence()
        self.__validate_household_and_family_unit_integrity()
        self.__validate_resident_membership()

    def __validate_resident_membership(self):
        if self.membership_count > 0:
            raise DomainException('Unable to proceed request, dual membership found.')
        
    def __validate_household_and_family_unit_integrity(self):
        if not self.household_id:
            raise DomainException("Household does not exist.")

        if not self.is_household_active:
            raise DomainException("Household is no longer active.")
        
        if not self.family_id:
            raise DomainException('Family does not exist.')

        if not self.is_family_active:
            raise DomainException('Family unit is no longer active.')
        
    def __validate_resident_existence(self):
        if not self.resident_id:
            raise DomainException("Resident does not exist")