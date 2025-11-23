from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class AnnouncementDTO:
    """Data Transfer Object for announcement operations"""
    announcement_id: Optional[int] = None
    announcement_title: Optional[str] = None
    announcement_body: Optional[str] = None
    announcement_created_at: Optional[datetime] = None
    announcement_status_id: Optional[int] = None
    announcement_published_at: Optional[datetime] = None
    announcement_expire_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    published_by_id: Optional[int] = None
    announcement_status_name: Optional[str] = None


@dataclass
class AnnouncementStatusDTO:
    """Data Transfer Object for announcement status"""
    announcement_status_id: int
    announcement_status_name: str