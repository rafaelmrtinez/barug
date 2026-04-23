from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ORDTO:
    or_id: int
    or_number: str
    payment_method: str
    amount_paid: float
    purpose: str
    issued_by_staff_id: Optional[int]
    issued_by_staff_code: Optional[str]
    issued_by_person_id: Optional[int]
    issued_by: Optional[str]
    issued_at: Optional[str]
    business_id: Optional[int]
    origin_type: Optional[str]
    origin_request_id: Optional[int]
    origin_request_code: Optional[str]
    origin_period_type: Optional[str]
    origin_period_year: Optional[int]
    origin_total_quote: Optional[float]
    clearance_rec_id: Optional[int]
    