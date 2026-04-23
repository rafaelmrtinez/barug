from dataclasses import dataclass
from typing import Optional
import uuid


@dataclass
class StaffCredential:
    staff_credential_id: Optional[uuid.UUID] = None
    username: Optional[str] = None
    passwordd: Optional[str] = None
    staff_id: Optional[int] = None
