from enum import Enum


class Relationships(Enum):
    HOUSEHOLD_HEAD = 1
    FAMILY_HEAD = 2
    SPOUSE = 3
    SON = 4
    DAUGHTER = 5
    PARENT = 6
    SIBLING = 7
    GRANDCHILD = 8
    GRANDPARENT = 9
    NEPHEW = 10
    NIECE = 11
    UNCLE = 12
    AUNT = 13
    COUSIN = 14
    IN_LAW = 15
    BOARDER = 16
    RENTER = 17
    DOMESTIC_HELPER = 18
    OTHER_RELATIVE = 19
    NON_RELATIVE = 20

    @classmethod
    def relationship_list(cls):
        return [i.value for i in cls]
