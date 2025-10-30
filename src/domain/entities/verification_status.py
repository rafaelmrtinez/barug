from dataclasses import dataclass
from typing import Optional


@dataclass
class VerificationStatusEntity:
    verification_status_id: Optional[int]
    verification_status_name: str
