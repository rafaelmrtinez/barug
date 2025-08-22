from enum import Enum

class HouseType(Enum):
    
    """Currently this is an enumm but I will be updating this soon since
    I think that the data of this enum can change over time and requires
    a table driven approach."""
    
    CONCRETE = 'concrete'
    SEMI_CONCRETE = 'semi_concrete'
    LIGHT_MATERIAL = 'light_material'

    @classmethod
    def list_house_types(cls):
        return [i.value for i in cls]