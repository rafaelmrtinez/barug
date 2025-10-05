from dataclasses import dataclass
from datetime import date


@dataclass
class BreastFeedingCheckRequest:
    check_date: date | None = None