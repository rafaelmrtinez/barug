from enum import Enum


class Relationship(Enum):
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
    
    @classmethod
    def map_relationship(cls, relation):
        if isinstance(relation, int):
            return cls.__int_relationship_mapper(relation)
        elif isinstance(relation, str):
            return cls.__string_relationship_mapper(relation)
        else:
            raise ValueError("Relationship must be an integer or a string.")
    
    @classmethod
    def __int_relationship_mapper(cls, relation: int) -> bool:
        try:
            print(f"Mapping integer relationship: {cls[relation]}")
            return cls[relation].value
        except KeyError:
            raise ValueError(
                f"Invalid relationship type: '{relation}'. "
                f"Valid options are: {[r.name for r in cls]}"
            )

    @classmethod
    def __string_relationship_mapper(cls, relation: str) -> int:
        normalized = relation.strip().upper().replace(" ", "_").replace("-", "_")
        try:
            return cls[normalized].value
        except KeyError:
            raise ValueError(
                f"Invalid relationship type: '{relation}'. "
                f"Valid options are: {[r.name for r in cls]}"
            )