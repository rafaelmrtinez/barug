from dataclasses import dataclass

@dataclass(frozen=True)
class ResidetDTO:
    person_id: int
    person_code: str
    full_name: str
    address: str
    mob_num: str
    email: str