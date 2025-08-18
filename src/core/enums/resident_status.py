from enum import Enum


class ResidentStatus(Enum):
    PENDING = 1
    RESIDENT = 2
    MOVED_OUT = 3
    MIGRATED = 4
    TRANSIENT = 5
    NON_RESIDENT = 6
    BUSINESS_OWNER = 7