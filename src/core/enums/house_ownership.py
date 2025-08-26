from enum import Enum


class HouseOwnership(Enum):
    
    """Currently this is an enumm but I will be updating this soon since
    I think that the data of this enum can change over time and requires
    a table driven approach."""
    
    OWNED = 1
    RENTED = 2
    FAMILY_OWNED = 3
    GOVERNMENT_HOUSING = 4
    INFORMAL_SETTLER = 5

    @classmethod
    def list_house_ownership_types(cls):
        return [i.value for i in cls]