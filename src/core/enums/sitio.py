from enum import Enum


class Sitio(Enum):

    """Currently this is an enumm but I will be updating this soon since
    I think that the data of this enum can change over time and requires
    a table driven approach."""
    
    COLON = "colon"
    BALINTAWAK = "balintawak"
    BOROMEO = "boromeo"
    MAGALLANES = "magallanes"
    KANIPAAN = "kanipaan"
    LUTAW_LUTAW = "lutaw_lutaw"
    CHINESE_FIL_COMMUNITY = "chinese_fil_community"
    PANGPANGO = "pangpango"
    MAUCO = "mauco"
    
    @classmethod
    def list_sitios(cls):
        return [i.value for i in cls]