from dataclasses import dataclass
from datetime import date


@dataclass
class ChildVitaminsRequest:
    dose_no: int | None = None
    date_given: date | None = None