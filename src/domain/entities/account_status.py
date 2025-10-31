from dataclasses import dataclass
from typing import Optional


@dataclass
class AccountStatus:
    acc_status_id: Optional[int]
    acc_status_name: str
