from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestStatusEntity:
    request_status_id: Optional[int]
    request_status_name: str
