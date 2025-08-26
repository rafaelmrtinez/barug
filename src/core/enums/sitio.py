from enum import Enum


class Sitio(Enum):

    """Currently this is an enumm but I will be updating this soon since
    I think that the data of this enum can change over time and requires
    a table driven approach."""
    
    COLON = 1
    BALINTAWAK = 2
    BOROMEO = 3
    MAGALLANES = 4
    KANIPAAN = 5
    LUTAW_LUTAW = 6
    CHINESE_FIL_COMMUNITY = 7
    PANGPANGO = 8
    MAUCO = 9

    @classmethod
    def list_sitios(cls):
        return [i.value for i in cls]