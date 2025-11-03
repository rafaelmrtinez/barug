from dataclasses import dataclass
from datetime import date

@dataclass
class ChildIronSupplementRequest:
    date_started: date | None = None
    date_completed: date | None = None