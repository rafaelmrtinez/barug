from dataclasses import dataclass
from typing import Optional


@dataclass
class TableAffected:
    table_affected_id: Optional[int]
    table_affected_name: str
