from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class StaffPurokAssignment:
    staff_purok_id: Optional[int] = None
    assigned_from: Optional[date] = None
    assigned_to: Optional[date] = None
    is_active: Optional[bool] = True
    purok_sitio_id: Optional[int] = None
    staff_id: Optional[int] = None
    staff_acc_req_id: Optional[int] = None
