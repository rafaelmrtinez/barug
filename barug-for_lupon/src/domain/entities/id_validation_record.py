from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class IDValidationRecord:
    id_validation_id: Optional[int] = None
    validation_date: Optional[datetime] = None
    remarks: Optional[str] = None
    person_id: Optional[int] = None
    validated_by_id: Optional[int] = None
    request_status_id: Optional[int] = None
