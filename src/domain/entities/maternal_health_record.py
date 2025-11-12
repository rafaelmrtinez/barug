from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MaternalHealthRecord:
    maternal_record_id: Optional[int]
    created_at: Optional[datetime]
    person_id: int
    husband_id: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    bmi_status_id: Optional[int] = None
    family_id: Optional[int] = None
    record_status_id: Optional[int] = None
    added_by_id: Optional[int] = None

    def bmi(self) -> Optional[float]:
        if self.weight is None or self.height is None or self.height == 0:
            return None
        try:
            return round(self.weight / ((self.height / 100.0) ** 2), 2)
        except Exception:
            return None
