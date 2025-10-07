from dataclasses import dataclass
from datetime import date


@dataclass
class BreastFeedingCheckRequest:
    date_order: int
    check_date: date | None = None