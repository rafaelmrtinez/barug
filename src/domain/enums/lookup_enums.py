from enum import Enum
from typing import Optional


class Sex(Enum):
    MALE = 'Male'
    FEMALE = 'Female'
    OTHER = 'Other'

    @classmethod
    def from_string(cls, v: Optional[str]):
        if not v:
            return None
        v = v.strip().lower()
        if v.startswith('m'):
            return cls.MALE
        if v.startswith('f'):
            return cls.FEMALE
        return cls.OTHER


class CivilStatus(Enum):
    SINGLE = 'Single'
    MARRIED = 'Married'
    WIDOWED = 'Widowed'
    SEPARATED = 'Separated'


class EmploymentStatus(Enum):
    EMPLOYED = 'Employed'
    UNEMPLOYED = 'Unemployed'
    SELF_EMPLOYED = 'Self-employed'
    RETIRED = 'Retired'


class RequestStatus(Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'


class VerificationStatus(Enum):
    VERIFIED = 'Verified'
    UNVERIFIED = 'Unverified'
    PENDING = 'Pending'
