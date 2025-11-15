from dataclasses import dataclass

@dataclass(frozen=True)
class ORDTO:
    or_id: int
    or_number: str
    payment_method_name: str
    amount_paid: float
    purpose: str
    issued_by: str
    issued_at: str