from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class CreateAnnouncementDraftCMD:
    """Command for creating an announcement draft"""
    title: str
    body: str
    created_by_id: int
    publish_at: Optional[datetime] = None
    expire_at: Optional[datetime] = None


@dataclass
class UpdateAnnouncementDraftCMD:
    """Command for updating an announcement draft"""
    announcement_id: int
    title: str
    body: str
    publish_at: Optional[datetime] = None
    expire_at: Optional[datetime] = None


@dataclass
class PublishAnnouncementCMD:
    """Command for publishing an announcement"""
    announcement_id: int
    published_by_id: int
    publish_at: Optional[datetime] = None