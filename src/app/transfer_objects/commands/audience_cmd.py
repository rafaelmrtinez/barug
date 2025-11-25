from dataclasses import dataclass
from typing import Optional, List


@dataclass
class AddAnnouncementAudienceCMD:
    """Command for adding audience to announcement"""
    announcement_id: int
    audience_scope_id: int
    role_id: Optional[int] = None
    purok_sitio_id: Optional[int] = None
    person_ids: Optional[List[int]] = None