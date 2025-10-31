from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LoginLog:
    login_log_id: Optional[int] = None
    login_time: Optional[datetime] = None
    logout_time: Optional[datetime] = None
    user_id: Optional[int] = None
    user_type_id: Optional[int] = None
