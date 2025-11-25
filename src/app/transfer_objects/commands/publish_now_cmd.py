from dataclasses import dataclass
from typing import Optional


@dataclass
class PublishAnnouncementNowCMD:
    """Command for publishing an announcement immediately"""
    announcement_id: int
    published_by_id: Optional[int] = None