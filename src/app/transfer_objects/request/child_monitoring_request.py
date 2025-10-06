from dataclasses import dataclass
from datetime import datetime

@dataclass
class ChildMonitoringRequest:
    check_date: datetime | None = None
    age: int | None = None
    wt: float | None = None
    temp: float | None = None
    ht: float | None = None
    findings: str | None = None
    notes: str | None = None