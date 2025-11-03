from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VerificationRecord:
    verification_id: Optional[int] = None
    verification_date: Optional[datetime] = None
    remarks: Optional[str] = None
    person_id: Optional[int] = None
    verified_by_id: Optional[int] = None
    verification_status_id: Optional[int] = None
