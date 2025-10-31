from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidIDType:
    valid_id_type_id: Optional[int]
    valid_id_type_name: str
