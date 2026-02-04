from dataclasses import dataclass
from typing import Optional


@dataclass
class SexLookup:
    sex_id: Optional[int]
    sex_name: str
