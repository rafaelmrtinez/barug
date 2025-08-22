from enum import Enum


class HouseOwnership(Enum):
    
    """Currently this is an enumm but I will be updating this soon since
    I think that the data of this enum can change over time and requires
    a table driven approach."""
    
    OWNED = 'owned'
    RENTED = 'rented'
    FAMILY_OWNED = 'family_owned'
    GOVERNMENT_HOUSING = 'government_housing'
    INFORMAL_SETTLER = 'informal_settler'
    
    @classmethod
    def list_house_ownership_types(cls):
        return [i.value for i in cls]