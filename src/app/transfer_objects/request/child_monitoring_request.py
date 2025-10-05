from dataclasses import dataclass
from datetime import date

@dataclass
class ChildMonitoringRequest:
    check_date: date | None = None
    age: int | None = None
    weight: float | None = None
    temperature: float | None = None
    height: float | None = None
    findings: str | None = None
    notes: str | None = None