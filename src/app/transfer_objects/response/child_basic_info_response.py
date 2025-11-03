from dataclasses import dataclass

@dataclass(frozen=True)
class BasicInformationResponse:
    fam_number: int
    child: str
    mother: str
    place_of_delivery: str
    birth_order: int
    mothers_age: int
    fathers_age: int
    father: str | None = None