from dataclasses import dataclass


from src.core.enums.person_status import PersonStatus
from src.core.enums.resident_status import ResidentStatus
from src.core.exceptions.domain_exceptions import DomainException
from src.core.exceptions.membership_exception import InvalidMembershipException


@dataclass(frozen=True)
class FamilyMembership:
    
    """This value object is used to enforce business rules
    for Family Unit Membership.
    
    NOTE: residency_status differs from resident_status
    
    residency_status refers to the following:
    - PENDING
    - RESIDENT
    - MOVED OUT
    - MIGRATED
    - TRANSIENT
    - NON RESIDENT
    - BUSINESS OWNER
    
    person_status on the other hand refers to:
    - ACTIVE
    - INACTIVE
    - PENDING

    Raises:
        DomainException: Resident does not exist
        DomainException: Household does not exist
        DomainException: Household is no longer active
        DomainException: Family does not exist
        DomainException: Family unit is no longer active
        DomainException: Unable to proceed request, dual membership found
    """
    
    resident_id: int
    household_id: int
    family_id: int
    is_household_active: bool
    is_family_active: bool
    membership_count: int
    residential_status: int
    person_status: int
    residency_period: int
    
    def validate_membership_request(self):
        self.__person_status_validity()
        self.__validate_resident_existence()
        self.__resident_status_validity()
        self.__residency_period_validity()
        self.__validate_household_and_family_unit_integrity()
        self.__validate_resident_membership()

    def __residency_period_validity(self):
        if self.residency_period < 1:
            raise DomainException("Residency period requirement can not be lesser than 1 month")

    def __person_status_validity(self):
        if self.person_status != PersonStatus.ACTIVE.value:
            raise DomainException("Residency status is currently not active.")

    def __resident_status_validity(self):
        allowed_status = [ResidentStatus.TRANSIENT.value, ResidentStatus.RESIDENT.value]
        if self.residential_status not in allowed_status:
            raise DomainException(f"Residency requirement is not met, only {ResidentStatus.RESIDENT.name.title()} and {ResidentStatus.TRANSIENT.name.title()} Residents are allowed.")

    def __validate_resident_membership(self):
        if self.membership_count > 1:
            raise DomainException("This resident is already registered in this family or another family record exists for them.")

        if self.membership_count < 1:
            raise InvalidMembershipException('Unable to proceed request, invalid membership found.')

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