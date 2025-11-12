from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PersonKinship:
    kinship_id: Optional[int] = None
    src_person_id: Optional[int] = None
    dst_person_id: Optional[int] = None
    relationship_id: Optional[int] = None
    is_active: Optional[bool] = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None
    added_at: Optional[datetime] = None
    added_by_id: Optional[int] = None
