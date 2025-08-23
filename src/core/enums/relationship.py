from enum import Enum


class Relationships(Enum):
    HOUSEHOLD_HEAD = "household"
    FAMILY_HEAD = "family head"
    SPOUSE = "spouse"
    SON = "son"
    DAUGHTER = "daughter"
    PARENT = "parent"
    SIBLING = "sibling"
    GRANDCHILD = "grandchild"
    GRANDPARENT = "grandparent"
    NEPHEW = "nephew"
    NIECE = "niece"
    UNCLE = "uncle"
    AUNT = "aunt"
    COUSIN = "cousing"
    IN_LAW = "in law"
    BOARDER = "boarder"
    RENTER = "renter"
    DOMESTIC_HELPER = "domestic helper"
    OTHER_RELATIVE = "other relative"
    NON_RELATIVE = "non relative"

    @classmethod
    def relationship_list(cls):
        return [i.value for i in cls]
