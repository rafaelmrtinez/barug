from dataclasses import dataclass
from typing import Optional


@dataclass
class LuponStaffSched:
    lupon_staff_sched_id: Optional[int] = None
    lupon_sched_id: Optional[int] = None
    staff_id: Optional[int] = None
    staff_acc_req_id: Optional[int] = None
