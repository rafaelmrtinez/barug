from dataclasses import dataclass
from datetime import date

@dataclass
class InitialChildImmunizationRequest:
    name: str | None = None
    d0: date | None = None
    d1: date | None = None
    d2: date | None = None
    d3: date | None = None
    wt24h: int | None = None
    stage: int | None = None