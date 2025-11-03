from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class StaffAccReqApproval:
    staff_acc_req_approval_id: Optional[int] = None
    approval_date: Optional[datetime] = None
    remarks: Optional[str] = None
    staff_acc_req_id: Optional[int] = None
    approved_by_id: Optional[int] = None
    request_status_id: Optional[int] = None
