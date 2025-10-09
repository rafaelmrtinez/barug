from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MaternalRecordBasicHistoryResponse:
    visit_date: date | None = None
    trimester: str | None = None
    weight: float | None = None
    danger_signs: str | None = None